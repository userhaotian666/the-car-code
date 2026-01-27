# schemas/car.py
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import datetime

# 导入摘要模型
from .common import DeviceSummary

# 小车状态 (沿用你提供的定义)
CAR_FAULT = 0       # 故障
CAR_STANDBY = 1     # 待机
CAR_RUNNING = 2     # 运行中

# --- 基础字段 ---
class CarBase(BaseModel):
    name: str
    status: int = 1  # 1-空闲
    
# --- 1. 创建模型 ---
class CarCreate(CarBase):
    # 可以在这里加额外的校验，比如名字不能为空
    name: str = Field(..., min_length=1, max_length=50)
    current_task_id: Optional[int] = None
    
# --- 2. 更新模型 ---
class CarUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[int] = None
    current_task_id: Optional[int] = None

class CarRead(CarBase):
    id: int
    created_at: datetime
    
    # 使用 Optional 是因为有些新车可能还没有历史状态数据
    status: Optional[int] = None
    
    # 如果你也想在状态接口返回位置和电量，可以继续添加：
    # battery: Optional[int] = None
    # longitude: Optional[float] = None
    # latitude: Optional[float] = None

    # 【重点】嵌套显示设备列表
    devices: List[DeviceSummary] = []

    # Pydantic V2 的标准写法，确保能兼容 SQLAlchemy 的异步 ORM 对象
    model_config = ConfigDict(from_attributes=True)