from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional
from database import get_db  # 假设你有一个获取 db 会话的依赖
from model import Problem   # 你的 SQLAlchemy 模型
from schemas import ProblemCreate, ProblemResponse, ProblemUpdate  # 你的 Pydantic 模型
router = APIRouter(prefix="/problems", tags=["problems"])

# --- 1. 【增】创建新问题 ---
@router.post("/", response_model=ProblemResponse)
def create_problem(obj_in: ProblemCreate, db: Session = Depends(get_db)):
    new_problem = Problem(
        task_id=obj_in.task_id,
        name=obj_in.name,
        description=obj_in.description
    )
    db.add(new_problem)
    db.commit()
    db.refresh(new_problem)
    return new_problem

# --- 2. 【查】获取问题列表 (支持按任务 ID 筛选) ---
@router.get("/", response_model=List[ProblemResponse])
def read_problems(task_id: Optional[int] = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    query = select(Problem)
    if task_id:
        query = query.where(Problem.task_id == task_id)
    
    # 按创建时间倒序排列
    query = query.order_by(Problem.created_at.desc()).offset(skip).limit(limit)
    result = db.execute(query).scalars().all()
    return result

# --- 3. 【查】获取单个问题详情 ---
@router.get("/{problem_id}", response_model=ProblemResponse)
def read_problem(problem_id: int, db: Session = Depends(get_db)):
    problem = db.get(Problem, problem_id)
    if not problem:
        raise HTTPException(status_code=404, detail="问题记录不存在")
    return problem

# --- 4. 【改】修改问题信息 ---
@router.put("/{problem_id}", response_model=ProblemResponse)
def update_problem(problem_id: int, obj_in: ProblemUpdate, db: Session = Depends(get_db)):
    problem = db.get(Problem, problem_id)
    if not problem:
        raise HTTPException(status_code=404, detail="问题记录不存在")
    
    # 动态更新传入的字段
    update_data = obj_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(problem, key, value)
    
    db.commit()
    db.refresh(problem)
    return problem

# --- 5. 【删】删除问题记录 ---
@router.delete("/{problem_id}")
def delete_problem(problem_id: int, db: Session = Depends(get_db)):
    problem = db.get(Problem, problem_id)
    if not problem:
        raise HTTPException(status_code=404, detail="问题记录不存在")
    
    db.delete(problem)
    db.commit()
    return {"message": f"问题 {problem_id} 已成功删除"}