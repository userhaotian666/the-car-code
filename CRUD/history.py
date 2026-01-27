# crud.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from model import CarHistory 

async def get_latest_car_status_async(db: AsyncSession, car_id: int):
    """
    使用 SQLAlchemy 2.0 风格的异步查询
    获取指定车辆最新的一条状态数据
    """
    # 1. 构建查询语句 (语句本身和同步版是一样的)
    stmt = (
        select(CarHistory)
        .where(CarHistory.car_id == car_id)
        .order_by(CarHistory.reported_at.desc())
        .limit(1)
    )
    
    # 2. 异步执行查询 (注意这里的 await)
    result = await db.execute(stmt)
    
    # 3. 获取单个结果
    # 注意：scalar_one_or_none() 是在内存中处理结果，通常不需要 await
    return result.scalar_one_or_none()