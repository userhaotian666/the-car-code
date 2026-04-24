from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CarRealtimeResponse(BaseModel):
    car_id: int
    battery: Optional[int] = Field(default=None, description="电量百分比")
    temperature: Optional[float] = Field(default=None, description="环境温度(℃)")
    speed: Optional[float] = Field(default=None, description="行驶速度(m/s)")
    signal: Optional[int] = Field(default=None, description="信号强度(RSSI/百分比)")
    longitude: Optional[float] = Field(default=None, description="地图相对X坐标")
    latitude: Optional[float] = Field(default=None, description="地图相对Y坐标")
    yaw: Optional[float] = Field(default=None, description="相对地图原点的朝向(度)")
    mode: Optional[int] = Field(default=None, description="小车模式: 1-遥控, 2-自主导航")
    car_status: Optional[int] = Field(
        default=None,
        description="车辆状态: 0-待机, 1-充电执行中, 2-任务执行中, 3-任务完成返回中, 4-异常状态",
    )
    work_status: Optional[int] = Field(
        default=None,
        description="车辆工作状态，由车端状态上报实时更新",
    )
    reported_at: datetime

    model_config = ConfigDict(from_attributes=True)
