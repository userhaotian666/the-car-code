# schemas/car.py
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import datetime

from car_status import CarStatus

# 导入摘要模型
from .common import DeviceSummary

# --- 基础字段 ---
class CarBase(BaseModel):
    name: str
    ip_address: str = Field(..., min_length=1, max_length=45, description="小车IP地址")
    status: int = Field(
        default=CarStatus.STANDBY.value,
        description="车辆状态: 0-待机, 1-充电执行中, 2-任务执行中, 3-任务完成返回中, 4-异常状态",
    )
    work_status: Optional[int] = Field(
        default=None,
        description="车辆工作状态，由车端状态上报实时更新",
    )
    
# --- 1. 创建模型 ---
class CarCreate(CarBase):
    # 可以在这里加额外的校验，比如名字不能为空
    name: str = Field(..., min_length=1, max_length=50)
    current_task_id: Optional[int] = None
    
# --- 2. 更新模型 ---
class CarUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = Field(default=None, min_length=1, max_length=45)
    status: Optional[int] = Field(
        default=None,
        description="只读字段，车辆状态只能由车端真实上报更新",
    )
    work_status: Optional[int] = Field(
        default=None,
        description="只读字段，车辆工作状态只能由车端真实上报更新",
    )
    current_task_id: Optional[int] = None

class CarRead(CarBase):
    id: int
    created_at: datetime
    
    # 使用 Optional 是因为有些新车可能还没有历史状态数据
    status: Optional[int] = None
    work_status: Optional[int] = None
    
    # 如果你也想在状态接口返回位置和电量，可以继续添加：
    # battery: Optional[int] = None
    # longitude: Optional[float] = None
    # latitude: Optional[float] = None

    # 【重点】嵌套显示设备列表
    devices: List[DeviceSummary] = []

    # Pydantic V2 的标准写法，确保能兼容 SQLAlchemy 的异步 ORM 对象
    model_config = ConfigDict(from_attributes=True)
