from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class CarRealtimeResponse(BaseModel):
    car_id: int
    battery: int = Field(..., description="电量百分比")
    
    # --- 新增字段 ---
    temperature: float = Field(..., description="环境温度(℃)")
    speed: float = Field(..., description="行驶速度(m/s)")
    signal: int = Field(..., description="信号强度(RSSI/百分比)")
    # ----------------
    
    longitude: float = Field(..., description="经度")
    latitude: float = Field(..., description="纬度")
    car_status: int
    reported_at: datetime

    class Config:
        # Pydantic V2 写法
        from_attributes = True