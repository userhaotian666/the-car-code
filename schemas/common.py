# schemas/common.py
from pydantic import BaseModel, ConfigDict

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