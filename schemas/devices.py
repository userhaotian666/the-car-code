from sqlalchemy import select
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime
from .common import CarSummary

# 基础模型，包含创建和更新时共有的字段
class DeviceBase(BaseModel):
    name: str
    status: int = 1
    device_type: Optional[str] = None
    ip_address: Optional[str] = None
    url: Optional[str] = None

# 创建时的模型 (继承 Base，name 必填已经在 Base 中定义)
class DeviceCreate(DeviceBase):
    pass

# 更新时的模型 (所有字段都变为可选，允许只更新部分字段)
class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[int] = None
    device_type: Optional[str] = None
    ip_address: Optional[str] = None
    url: Optional[str] = None

# 读取/返回时的模型 (包含 ID 和 时间字段)
class DeviceRead(DeviceBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    # 【重点】嵌套显示车辆列表
    # 这里的 CarSummary 来自 common.py
    cars: List[CarSummary] = [] 

    model_config = ConfigDict(from_attributes=True)
