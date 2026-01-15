# schemas.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class CarRealtimeResponse(BaseModel):
    car_id: int
    battery: int = Field(..., description="电量百分比")
    longitude: float = Field(..., description="经度")
    latitude: float = Field(..., description="纬度")
    car_status: int
    reported_at: datetime

    class Config:
        # Pydantic V2 写法 (如果是 V1 用 orm_mode = True)
        from_attributes = True