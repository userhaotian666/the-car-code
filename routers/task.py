from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime

from database import get_db
from model import Task, Path, Car
from schemas import TaskCreate, TaskRead

router = APIRouter(prefix="/tasks", tags=["Tasks"])

# ================= 状态常量定义 =================
TASK_UNSTARTED = 0
TASK_RUNNING = 1
TASK_PAUSED = 2
TASK_COMPLETED = 3
TASK_FAULT = 4

CAR_FAULT = 0
CAR_STANDBY = 1
CAR_RUNNING = 2

# ==========================================
# 1. 创建任务 (Create)
# ==========================================
@router.post("/", response_model=TaskRead, status_code=status.HTTP_201_CREATED, summary="创建基础任务")
async def create_task(task_in: TaskCreate, db: AsyncSession = Depends(get_db)):
    db_task = Task(**task_in.model_dump())
    db.add(db_task)
    await db.commit()      # 👈 异步提交
    await db.refresh(db_task) # 👈 异步刷新
    return db_task

# ==========================================
# 2. 绑定路径 (Bind Path)
# ==========================================
@router.put("/{task_id}/bind_path/{path_id}", response_model=TaskRead, summary="给任务绑定路径")
async def bind_path_to_task(task_id: int, path_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    path = await db.get(Path, path_id)
    if not path:
        raise HTTPException(status_code=404, detail="Path not found")
        
    task.path_id = path.id
    await db.commit()
    await db.refresh(task)
    return task

# ==========================================
# 3. 指派车辆 (Assign Car)
# ==========================================
@router.post("/{task_id}/assign_car/{car_id}", summary="指派车辆（仅绑定）")
async def assign_car_to_task(task_id: int, car_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    car = await db.get(Car, car_id)
    
    if not task or not car:
        raise HTTPException(status_code=404, detail="任务或车辆不存在")
    
    if car.status == CAR_FAULT:
         raise HTTPException(status_code=400, detail="车辆故障，无法指派")
    
    if car.status == CAR_RUNNING:
        raise HTTPException(status_code=400, detail="车辆正在运行中")

    # 建立异步关联
    car.current_task = task
    task.status = TASK_UNSTARTED
    
    await db.commit()
    return {"message": f"车辆 {car.name} 已指派给任务 {task.name}", "success": True}

# ==========================================
# 4. 开始任务 (Start)
# ==========================================
@router.post("/{task_id}/start", summary="开始/继续任务")
async def start_task(task_id: int, db: AsyncSession = Depends(get_db)):
    # 显式加载 executor 以便修改小车状态
    stmt = select(Task).options(selectinload(Task.executor)).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalars().first()

    if not task or not task.executor:
        raise HTTPException(status_code=400, detail="任务不存在或未分配车辆")

    if task.executor.status == CAR_FAULT:
        raise HTTPException(status_code=400, detail="指派的车辆处于故障状态")

    task.status = TASK_RUNNING
    task.executor.status = CAR_RUNNING
    
    await db.commit()
    return {"message": "任务已启动", "task_status": task.status, "car_status": task.executor.status}

# ==========================================
# 5. 暂停任务 (Pause)
# ==========================================
@router.post("/{task_id}/pause", summary="暂停任务")
async def pause_task(task_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Task).options(selectinload(Task.executor)).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalars().first()

    if not task or task.status != TASK_RUNNING:
        raise HTTPException(status_code=400, detail="任务未在运行中，无法暂停")

    task.status = TASK_PAUSED
    if task.executor:
        task.executor.status = CAR_STANDBY

    await db.commit()
    return {"message": "任务已暂停"}

# ==========================================
# 6. 完成任务 (Finish)
# ==========================================
@router.post("/{task_id}/finish", summary="完成任务")
async def finish_task(task_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Task).options(selectinload(Task.executor)).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalars().first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = TASK_COMPLETED
    task.finished_at = datetime.now()

    if task.executor:
        task.executor.status = CAR_STANDBY
        task.executor.current_task_id = None # 释放车辆
    
    await db.commit()
    return {"message": "任务已顺利完成", "success": True}

# ==========================================
# 7. 查询列表 (Read List)
# ==========================================
@router.get("/", response_model=List[TaskRead], summary="获取任务列表")
async def read_tasks(
    skip: int = 0, 
    limit: int = 100, 
    status: Optional[int] = None, 
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Task).options(
        selectinload(Task.path_info),
        selectinload(Task.executor)
    )
    
    if status is not None:
        stmt = stmt.where(Task.status == status)
        
    stmt = stmt.order_by(Task.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/{task_id}", response_model=TaskRead, summary="获取单个任务详情")
async def read_task(task_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Task).options(
        selectinload(Task.path_info),
        selectinload(Task.executor)
    ).where(Task.id == task_id)
    
    result = await db.execute(stmt)
    task = result.scalars().first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.get("/{task_id}/status", summary="获取任务当前状态")
async def get_task_status(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task.id, "status": task.status}

# ==========================================
# 8. 删除任务 (Delete)
# ==========================================
@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除任务并释放资源")
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Task).options(selectinload(Task.executor)).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalars().first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.executor:
        task.executor.status = CAR_STANDBY
        task.executor.current_task_id = None

    await db.delete(task)
    await db.commit()
    return None