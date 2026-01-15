# crud.py
from sqlalchemy.orm import Session
from sqlalchemy import select
from model import CarHistory  # 假设你的 CarHistory 在 models.py 里

def get_latest_car_status_sync(db: Session, car_id: int):
    """
    使用 SQLAlchemy 2.0 风格的同步查询
    获取指定车辆最新的一条状态数据
    """
    # 1. 构建查询语句 (2.0 风格)
    stmt = (
        select(CarHistory)
        .where(CarHistory.car_id == car_id)
        .order_by(CarHistory.reported_at.desc())
        .limit(1)
    )
    
    # 2. 执行查询 (同步执行)
    result = db.execute(stmt)
    
    # 3. 获取单个结果 (如果没有结果返回 None)
    # scalar_one_or_none() 是 2.0 推荐的获取单条数据的方法
    return result.scalar_one_or_none()