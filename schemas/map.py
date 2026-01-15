from pydantic import BaseModel

# 创建地图时，前端传来的数据
class MapCreate(BaseModel):
    name: str
    center_lat: float
    center_lng: float
    zoom: int = 16 # 默认值

# 返回给前端的数据
class MapOut(BaseModel):
    id: int
    name: str
    center_lat: float
    center_lng: float
    zoom: int
    
    class Config:
        from_attributes = True