from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from database import SessionLocal  # 👈 【关键】请引入你自己定义的 SessionLocal
from CRUD import get_latest_car_status_sync # 假设你的查询函数在这里
from schemas import CarRealtimeResponse # 假设你的模型在这里
import asyncio
from fastapi.encoders import jsonable_encoder

router = APIRouter(prefix="/history", tags=["history"])

@router.websocket("/{car_id}/monitor")
async def websocket_car_monitor(
    websocket: WebSocket, 
    car_id: int
    # ❌ 删除这里的 db: Session = Depends(get_db)
    # 这一行导致连接一直被占用不释放
):
    print(f"🔌 [连接请求] 正在连接车辆: {car_id}")
    await websocket.accept()
    
    last_reported_time = None
    
    try:
        while True:
            # ✅ 【核心修改】每次循环使用 with 语句创建新的临时会话
            # 这里的 SessionLocal() 会从连接池借一个连接，
            # with 代码块结束时，会自动 close() 并归还连接。
            with SessionLocal() as db:
                
                # 1. 查询数据
                try:
                    # 注意：因为每次都是新的 Session，所以不需要 db.commit() 来刷新数据了
                    # 新 Session 默认就能看到数据库里的最新状态。
                    car_data = get_latest_car_status_sync(db, car_id)
                except Exception as e:
                    print(f"❌ [DB错误] {e}")
                    await asyncio.sleep(1) 
                    continue

                if car_data:
                    # 2. 判断数据是否更新
                    if last_reported_time != car_data.reported_at:
                        data_model = CarRealtimeResponse.model_validate(car_data)
                        data_json = jsonable_encoder(data_model)
                        
                        await websocket.send_json(data_json)
                        # print(f"📤 [推送] 数据已发送: {data_json['reported_at']}")
                        
                        last_reported_time = car_data.reported_at
            
            # 3. 频率控制 (让出 CPU 并防止频繁查询)
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        print(f"👋 客户端断开")
    except Exception as e:
        print(f"❌ 异常: {e}")
        # 这里不需要 db.close()，因为 with 语句已经自动处理了
        await websocket.close()