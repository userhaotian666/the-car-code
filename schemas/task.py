from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from datetime import datetime,time,date
from .common import PathSimple, CarSimple, ProblemSimple

# 基础模型：添加新增字段
class TaskBase(BaseModel):
    name: str
    status: int = 0  # 建议使用 IntEnum，但在 Pydantic 中 int 也能兼容
    map_id: Optional[int] = None
    
    # --- 新增部分 ---
    is_scheduled: bool = Field(default=False, description="是否为定时任务: 0-否, 1-是")
    scheduled_start: Optional[time] = Field(None, description="定时开始时间")
    scheduled_end: Optional[time] = Field(None, description="定时结束时间")
    # ----------------

# 1. 创建任务时的请求体
class TaskCreate(TaskBase):
    """
    创建任务时，如果标记为定时任务，建议校验时间必填
    """
    @model_validator(mode='after')
    def check_schedule_times(self):
        # Pydantic v2 写法 (如果是 v1 使用 @root_validator)
        if self.is_scheduled and not self.scheduled_start:
            raise ValueError('如果是定时任务，必须提供开始时间 (scheduled_start)')
        return self

# --- 核心：任务响应模型 ---
class TaskRead(BaseModel):
    id: int
    name: str
    status: int
    map_id: Optional[int]
    
    # --- 新增部分：响应中也需要包含这些信息 ---
    is_scheduled: bool
    scheduled_start: Optional[time]
    scheduled_end: Optional[time]
    # ---------------------------------------

    # 嵌套显示对象
    path_info: Optional[PathSimple] = None 
    executor: Optional[CarSimple] = None
    problems: Optional[List[ProblemSimple]] = None   
    
    created_at: datetime
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True