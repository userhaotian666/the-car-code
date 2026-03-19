import asyncio  # 必须引入这个来代替 time
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

# 导入你的 database 配置
from database import AsyncSessionLocal, get_db
# 导入你的模型
from model import Command, CarHistory 
# 导入请求模型
from schemas import ReturnToBaseRequest

# === 预设基站坐标 ===
BASE_STATION_LNG = 121.560037
BASE_STATION_LAT = 25.039462

async def simulate_return_trip(command_id: int, car_id: int):
    """
    异步后台任务：
    """
    # === 预设基站坐标 ===
    BASE_STATION_LNG = 120.074429
    BASE_STATION_LAT = 30.135510
    
    # 定义判定范围 (阈值)，0.00005 约等于 5米范围
    THRESHOLD = 0.00005 

    async with AsyncSessionLocal() as db:
        try:
            # --- 步骤 1: 异步查询当前位置 ---
            stmt = select(CarHistory)\
                .where(CarHistory.car_id == car_id)\
                .order_by(CarHistory.reported_at.desc())\
                .limit(1)
            
            result = await db.execute(stmt)
            last_record = result.scalars().first()

            if not last_record:
                print(f"⚠️ 车辆 {car_id} 无历史记录，无法判断位置。")
                # 这里可以选择设定一个默认起点，或者直接报错退出
                # 为了健壮性，这里假设如果没有记录，则默认为不在基站，给个默认起点
                start_lng, start_lat = 121.500000, 25.000000 
            else:
                start_lng = float(last_record.longitude)
                start_lat = float(last_record.latitude)
                print(f"📍 [异步] 获取到车辆起点: ({start_lat}, {start_lng})")

            # ====================================================
            # 🔥 新增功能：检查是否已在基站 (Check if already at base)
            # ====================================================
            is_at_base = (
                abs(start_lng - BASE_STATION_LNG) < THRESHOLD and 
                abs(start_lat - BASE_STATION_LAT) < THRESHOLD
            )

            if is_at_base:
                print(f"🛑 车辆 {car_id} 已经在基站范围内，取消返航任务。")
                
                # 更新命令状态为 3 (Failed / Cancelled)
                cmd_result = await db.execute(select(Command).where(Command.id == command_id))
                cmd = cmd_result.scalars().first()
                if cmd:
                    cmd.status = 3  # 3 代表失败或取消
                    cmd.finished_at = datetime.now()
                    # 这里可以将 command_type 或其他字段备注改为 "ALREADY_AT_BASE" 以便前端展示
                    await db.commit()
                
                # ⛔ 直接结束函数，不执行后续逻辑
                return 

            # ====================================================
            # 下面是正常的返航逻辑
            # ====================================================

            # --- 步骤 2: 更新命令状态为正在执行 ---
            cmd_result = await db.execute(select(Command).where(Command.id == command_id))
            cmd = cmd_result.scalars().first()
            
            if cmd:
                cmd.status = 1  # Executing
                await db.commit()

            # --- 步骤 3: 路径规划 ---
            TOTAL_TIME = 15
            INTERVAL = 0.5
            STEPS = int(TOTAL_TIME / INTERVAL)

            lng_step = (BASE_STATION_LNG - start_lng) / STEPS
            lat_step = (BASE_STATION_LAT - start_lat) / STEPS

            curr_lng = start_lng
            curr_lat = start_lat

            print(f"🚗 车辆 {car_id} 开始自动返航 (Async)...")

            for _ in range(STEPS):
                curr_lng += lng_step
                curr_lat += lat_step

                history = CarHistory(
                    car_id=car_id,
                    battery=70,  
                    temperature=37.0,
                    speed=12.0,
                    signal=5,
                    longitude=round(curr_lng, 7),
                    latitude=round(curr_lat, 7),
                    car_status=2, 
                    reported_at=datetime.now()
                )
                
                db.add(history)
                await db.commit()
                
                await asyncio.sleep(INTERVAL)

            # --- 步骤 4: 完成 ---
            final_fix = CarHistory(
                car_id=car_id,
                battery=69, temperature=37.0, speed=0, signal=5,
                longitude=BASE_STATION_LNG,
                latitude=BASE_STATION_LAT,
                car_status=0,
                reported_at=datetime.now()
            )
            db.add(final_fix)
            
            # 重新获取 cmd (为了安全起见，防止 session 过期)
            cmd_result = await db.execute(select(Command).where(Command.id == command_id))
            cmd = cmd_result.scalars().first()
            
            if cmd:
                cmd.status = 2 # Success
                cmd.finished_at = datetime.now()
            
            await db.commit()
            print(f"✅ 车辆 {car_id} 已自动抵达基站 (Async)。")

        except Exception as e:
            print(f"❌ 异步仿真失败: {e}")
            await db.rollback()

router = APIRouter(prefix="/commands", tags=["commands"])

@router.post("/return_base")
async def return_to_base(
    req: ReturnToBaseRequest, 
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db) # 注入的是 AsyncSession
):
    try:
        # 1. 记录命令 (异步写法)
        new_command = Command(
            car_id=req.car_id,
            command_type="RETURN_TO_BASE",
            status=0, 
            created_at=datetime.now()
        )
        db.add(new_command)
        await db.commit()        # ⚠️ Await
        await db.refresh(new_command) # ⚠️ Await
        
        # 2. 启动后台任务
        # FastAPI 非常智能，如果 add_task 传入的是 async 函数，它会自动在事件循环中调度
        background_tasks.add_task(
            simulate_return_trip,
            command_id=new_command.id,
            car_id=req.car_id
        )
        
        return {
            "code": 200, 
            "message": "自动返航指令已确认", 
            "data": {"command_id": new_command.id}
        }
        
    except Exception as e:
        await db.rollback() # ⚠️ Await
        raise HTTPException(status_code=500, detail=str(e))