# schemas/common.py
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any
from datetime import datetime
# --- 基础配置 ---
# Pydantic v2 必须配置这个，才能读取 SQLAlchemy 的 ORM 对象
orm_config = ConfigDict(from_attributes=True)

# --- 1. 车辆摘要 (给 Device 用) ---
class CarSummary(BaseModel):
    id: int
    name: str
    status: int  # 只带最关键的状态
    
    model_config = orm_config

# --- 2. 设备摘要 (给 Car 用) ---
class DeviceSummary(BaseModel):
    id: int
    name: str
    status: int
    device_type: str | None = None # Python 3.10+ 写法，等同于 Optional[str]
    
    model_config = orm_config


# 用于展示任务信息的模型
class PathSimple(BaseModel):
    id: int
    name: str
    # waypoints: List[Any] = [] # 列表页可能不需要显示具体的坐标点，为了性能可省略
    
    class Config:
        from_attributes = True

# 简单的小车模型，用于在任务里显示
class CarSimple(BaseModel):
    id: int
    name: str
    status: int

    class Config:
        from_attributes = True

