from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from database import AsyncSessionLocal  # 👈 确保这是你定义的异步 Session 工厂
from CRUD import get_latest_car_status_async  # 👈 使用我们之前改好的异步查询函数
from schemas import CarRealtimeResponse
import asyncio
from fastapi.encoders import jsonable_encoder

router = APIRouter(prefix="/history", tags=["history"])

@router.websocket("/{car_id}/monitor")
async def websocket_car_monitor(
    websocket: WebSocket, 
    car_id: int
):
    print(f"🔌 [连接请求] 正在异步监控车辆: {car_id}")
    await websocket.accept()
    
    last_reported_time = None
    has_logged_empty_state = False
    
    try:
        while True:
            # ✅ 【核心修改 1】使用 async with 开启异步会话
            # 这样每次循环都会从异步连接池借出一个连接，结束后自动归还
            async with AsyncSessionLocal() as db:
                
                try:
                    # ✅ 【核心修改 2】必须 await 异步查询函数
                    car_data = await get_latest_car_status_async(db, car_id)
                except Exception as e:
                    print(f"❌ [DB错误] {e}")
                    await asyncio.sleep(1) 
                    continue

                if car_data:
                    has_logged_empty_state = False
                    # 2. 判断数据是否更新
                    if last_reported_time != car_data.reported_at:
                        # 验证并转换模型
                        data_model = CarRealtimeResponse.model_validate(car_data)
                        data_json = jsonable_encoder(data_model)
                        
                        # 发送数据到前端
                        await websocket.send_json(data_json)
                        print(
                            "📡 [WebSocket] 已推送车辆状态: "
                            f"car_id={car_id}, reported_at={car_data.reported_at}, speed={car_data.speed}"
                        )
                        
                        # 更新最后一次记录的时间戳
                        last_reported_time = car_data.reported_at
                elif not has_logged_empty_state:
                    print(f"ℹ️ [WebSocket] 车辆 {car_id} 暂无可推送的历史状态")
                    has_logged_empty_state = True
            
            # 3. 频率控制 (让出事件循环，防止死循环卡死服务器)
            # 建议根据你传感器上报的频率调整，比如 0.5 秒或 1 秒
            await asyncio.sleep(1.0)
            
    except WebSocketDisconnect:
        print(f"👋 客户端 {car_id} 已断开连接")
    except Exception as e:
        print(f"❌ WebSocket 异常: {e}")
        try:
            await websocket.close()
        except:
            pass
