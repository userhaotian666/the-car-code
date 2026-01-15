import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, APIRouter
from sqlalchemy.orm import Session
from fastapi.encoders import jsonable_encoder

# 引入我们刚才写的文件
from database import get_db  # 假设你有个 database.py 获取 session
from CRUD import get_latest_car_status_sync
from schemas import CarRealtimeResponse

router = APIRouter(prefix="/history", tags=["history"])

@router.websocket("/{car_id}/monitor")
async def websocket_car_monitor(
    websocket: WebSocket, 
    car_id: int, 
    db: Session = Depends(get_db)
):
    print(f"🔌 [连接请求] 正在连接车辆: {car_id}")
    await websocket.accept()
    
    last_reported_time = None
    
    try:
        while True:
            # ==========================================
            # ⚡️【核心修复】⚡️
            # 强制提交一次事务，打破“快照”效应，让 Session 看到最新的数据
            db.commit() 
            # ==========================================

            # 1. 查询数据
            try:
                car_data = get_latest_car_status_sync(db, car_id)
            except Exception as e:
                print(f"❌ [DB错误] {e}")
                # 遇到数据库错误稍微停一下，防止死循环刷屏
                await asyncio.sleep(1) 
                continue

            if car_data:
                # 2. 打印调试：看看查出来的时间到底变没变
                # print(f"🔍 DB最新时间: {car_data.reported_at}") 

                if last_reported_time != car_data.reported_at:
                    data_model = CarRealtimeResponse.model_validate(car_data)
                    data_json = jsonable_encoder(data_model)
                    
                    await websocket.send_json(data_json)
                    print(f"📤 [推送] 数据已发送: {data_json['reported_at']}")
                    
                    last_reported_time = car_data.reported_at
            
            # 3. 频率控制
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        print(f"👋 客户端断开")
    except Exception as e:
        print(f"❌ 异常: {e}")
        await websocket.close()