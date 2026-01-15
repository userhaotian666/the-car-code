from pydantic import BaseModel
from typing import List

# 1. 定义单个坐标点
class Waypoint(BaseModel):
    lat: float
    lng: float

# 2. 定义前端发来的请求体
class MissionCreateRequest(BaseModel):
    #map_id: int              # 在哪张地图上点的
    car_id: int              # 指定哪辆车去跑
    name: str                # 任务名字，例如 "A区巡逻"
    waypoints: List[Waypoint] # 包含多个坐标点的列表