from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# 1. 定义单个坐标点的模型
# 前端传过来的点通常包含经纬度 (lat, lng) 或者 x, y
class Waypoint(BaseModel):
    x:float = Field(..., description="经度 (Longitude) 或 X坐标")
    y: float = Field(..., description="纬度 (Latitude) 或 Y坐标")

 

# 2. 创建路径时的请求体 (Request Body)
class PathCreate(BaseModel):
    name: str = Field(..., max_length=100, description="路径名称")
    # 这里定义为 Waypoint 对象列表，FastAPI 会自动验证格式，
    # 存入数据库时 SQLAlchemy 会自动将其转为 JSON List
    waypoints: List[Waypoint] 

# 3. 响应体 (Response Model)
class PathRead(BaseModel):
    id: int
    name: str
    waypoints: List[Waypoint] # 或者 List[Waypoint]

    class Config:
        from_attributes = True # 兼容 ORM 模型 (旧版为 orm_mode = True)

class PathUpdate(BaseModel):
    name: Optional[str] = None
    waypoints: Optional[List[Waypoint]] = None