from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List

# 创建问题时的请求体
class ProblemCreate(BaseModel):
    task_id: Optional[int] = None
    name: str
    description: Optional[str] = None

# 更新问题时的请求体（所有字段可选）
class ProblemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    task_id: Optional[int] = None

# 返回数据时的格式
class ProblemResponse(BaseModel):
    id: int
    task_id: Optional[int]
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)