from pydantic import BaseModel, Field
from typing import List, Optional

# 单个路径点统一使用 [x, y] 二元数组格式。
Waypoint = tuple[float, float]

# 2. 创建路径时的请求体 (Request Body)
class PathCreate(BaseModel):
    name: str = Field(..., max_length=100, description="路径名称")
    waypoints: List[Waypoint] = Field(..., description="路径点列表，格式为 [[x, y], ...]")

# 3. 响应体 (Response Model)
class PathRead(BaseModel):
    id: int
    name: str
    waypoints: List[Waypoint]

    class Config:
        from_attributes = True # 兼容 ORM 模型 (旧版为 orm_mode = True)

class PathUpdate(BaseModel):
    name: Optional[str] = None
    waypoints: Optional[List[Waypoint]] = None
