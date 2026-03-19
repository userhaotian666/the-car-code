# app/mqtt/client.py
import asyncio
import json
import aiomqtt
from sqlalchemy import select  # 引入 select 用于异步查询
from database import AsyncSessionLocal  # ⚠️ 注意：这里改为导入你的异步会话工厂，而不是 get_db
from model import CarHistory,Car

BROKER_ADDRESS = "broker.emqx.io"
TOPIC_LOCATION = "fire_car/+/location"

async def process_car_data(topic: str, data: dict):
    """处理解析后的小车数据并入库"""
    device_id = data.get("device_id")
    x = data.get("x",0.0)
    y = data.get("y",0.0)
    status = data.get("status",0)
    
    # 使用 async with 自动管理会话的生命周期 (相当于自动执行 close)
    async with AsyncSessionLocal() as db:
        try:
            # 1. 构建异步查询语句
            stmt = select(Car).where(Car.id == device_id)
            # 2. 异步执行查询
            result = await db.execute(stmt)
            # 3. 提取结果
            car = result.scalars().first()
            
            if car:
                # 2. 如果查到这辆车，构造一条历史记录
                # (这里的字段名称取决于你的 CarHistory 模型定义，请根据实际情况调整)
                new_history = CarHistory(
                    car_id=device_id,  # 关联的外键 ID
                    longitude=x,
                    latitude=y,
                    car_status=status
                )
                
                # 将新记录添加到会话中
                db.add(new_history)
                await db.commit()
                print(f"已经发送数据: {device_id}")
            else:
                print(f"⚠️ 忽略未知设备数据: {device_id}")
                
        except Exception as e:
            # 5. 异步回滚
            await db.rollback()
            print(f"❌ 数据库操作异常: {e}")

async def mqtt_listener():
    """持续监听 MQTT 消息的后台任务"""
    async with aiomqtt.Client(BROKER_ADDRESS) as client:
        await client.subscribe(TOPIC_LOCATION)
        print(f"✅ MQTT 监听已启动，订阅主题: {TOPIC_LOCATION}")
        
        async for message in client.messages:
            try:
                payload_str = message.payload.decode()
                data = json.loads(payload_str)
                # 异步执行入库操作，不阻塞监听
                asyncio.create_task(process_car_data(str(message.topic), data))
            except json.JSONDecodeError:
                pass
            except Exception as e:
                print(f"❌ 解析消息出错: {e}")