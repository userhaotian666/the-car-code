from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from database import get_db
from model import Problem
from schemas import ProblemCreate, ProblemResponse, ProblemUpdate

router = APIRouter(prefix="/problems", tags=["Problems"])

# ==========================================
# 1. 创建问题记录 (Create)
# ==========================================
@router.post("/", response_model=ProblemResponse, status_code=status.HTTP_201_CREATED)
async def create_problem(obj_in: ProblemCreate, db: AsyncSession = Depends(get_db)):
    """
    异步创建报错记录。
    """
    new_problem = Problem(
        task_id=obj_in.task_id,
        name=obj_in.name,
        description=obj_in.description
    )
    db.add(new_problem)
    
    await db.commit()    # 👈 必须 await
    await db.refresh(new_problem) # 👈 必须 await
    return new_problem

# ==========================================
# 2. 获取问题列表 (Read List)
# ==========================================
@router.get("/", response_model=List[ProblemResponse])
async def read_problems(
    task_id: Optional[int] = None, 
    skip: int = 0, 
    limit: int = 100, 
    db: AsyncSession = Depends(get_db)
):
    """
    异步查询列表，支持按任务 ID 筛选并按时间倒序。
    """
    stmt = select(Problem)
    if task_id:
        stmt = stmt.where(Problem.task_id == task_id)
    
    # 按照创建时间倒序排列，并进行分页
    stmt = stmt.order_by(Problem.created_at.desc()).offset(skip).limit(limit)
    
    # 执行异步查询
    result = await db.execute(stmt)
    return result.scalars().all()

# ==========================================
# 3. 获取单个问题详情 (Read One)
# ==========================================
@router.get("/{problem_id}", response_model=ProblemResponse)
async def read_problem(problem_id: int, db: AsyncSession = Depends(get_db)):
    """
    使用异步 get 方式获取主键记录。
    """
    problem = await db.get(Problem, problem_id) # 👈 必须 await
    if not problem:
        raise HTTPException(status_code=404, detail="问题记录不存在")
    return problem

# ==========================================
# 4. 修改问题信息 (Update)
# ==========================================
@router.put("/{problem_id}", response_model=ProblemResponse)
async def update_problem(problem_id: int, obj_in: ProblemUpdate, db: AsyncSession = Depends(get_db)):
    """
    异步更新问题描述。
    """
    problem = await db.get(Problem, problem_id)
    if not problem:
        raise HTTPException(status_code=404, detail="问题记录不存在")
    
    # 提取更新字段 (忽略前端未传的字段)
    update_data = obj_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(problem, key, value)
    
    await db.commit()
    await db.refresh(problem)
    return problem

# ==========================================
# 5. 删除问题记录 (Delete)
# ==========================================
@router.delete("/{problem_id}")
async def delete_problem(problem_id: int, db: AsyncSession = Depends(get_db)):
    """
    异步删除问题记录。
    """
    problem = await db.get(Problem, problem_id)
    if not problem:
        raise HTTPException(status_code=404, detail="问题记录不存在")
    
    await db.delete(problem) # 👈 异步删除
    await db.commit()        # 👈 必须 await
    return {"message": f"问题 {problem_id} 已成功删除"}