from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from .common import PathSimple, CarSimple,ProblemSimple
# 基础模型
class TaskBase(BaseModel):
    name: str
    status:int = 0
    map_id: Optional[int] = None # 任务通常属于某个地图，可选

# 1. 创建任务时的请求体
class TaskCreate(TaskBase):
    pass

# --- 核心：任务响应模型 ---
class TaskRead(BaseModel):
    id: int
    name: str
    status: int
    map_id: Optional[int]
    
    # 关键：嵌套显示对象，而不是只显示 path_id
    # 如果没绑定，则是 None
    path_info: Optional[PathSimple] = None 
    executor: Optional[CarSimple] = None
    problems: Optional[List["ProblemSimple"]] = None   
    
    created_at: datetime
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True