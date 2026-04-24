from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from typing import List

from car_runtime import get_assignment_block_reason, get_effective_car_status
from database import get_db
from model import Car, Task, Path, TaskStatus
from schemas import MissionCreateRequest

router = APIRouter(prefix="/missions", tags=["Missions"])

# ==========================================
# 1. 任务下发 (Dispatch)
# ==========================================
@router.post("/dispatch", status_code=status.HTTP_201_CREATED, summary="下发任务并指派车辆")
async def dispatch_mission(request: MissionCreateRequest, db: AsyncSession = Depends(get_db)):
    # 1. 获取车辆并检查状态
    stmt = (
        select(Car)
        .options(selectinload(Car.current_task))
        .where(Car.id == request.car_id)
    )
    result = await db.execute(stmt)
    car = result.scalars().first()
    if not car:
        raise HTTPException(status_code=404, detail=f"找不到 ID 为 {request.car_id} 的车辆")

    block_reason = get_assignment_block_reason(car)
    if block_reason:
        raise HTTPException(status_code=400, detail=block_reason)

    # 2. 异步创建路径记录
    # model_dump 将 Pydantic 列表转为 Python 列表，以便存入 JSON 字段
    waypoints_data = [[float(p.lat), float(p.lng)] for p in request.waypoints]
    
    new_path = Path(
        name=f"{request.name}_Path", 
        waypoints=waypoints_data
    )
    db.add(new_path)
    # flush 的作用是提前拿到数据库生成的 path.id，但不结束事务
    await db.flush() 

    # 3. 异步创建任务记录
    new_task = Task(
        name=request.name, 
        path_id=new_path.id, 
        status=TaskStatus.PENDING,
    )
    db.add(new_task)
    await db.flush() # 拿到 task.id

    # 4. 仅建立车辆与任务的绑定关系，车辆状态保持由车端真实上报驱动
    car.current_task_id = new_task.id
    
    # 5. 统一提交事务
    await db.commit()
    
    return {
        "message": "任务已成功下发", 
        "task_id": new_task.id,
        "path_id": new_path.id
    }

# ==========================================
# 2. 查询任务执行者 (Get Executor)
# ==========================================
@router.get("/tasks/{task_id}/executor", summary="获取任务的执行车辆详情")
async def get_task_executor(task_id: int, db: AsyncSession = Depends(get_db)):
    # 使用 selectinload 预加载 executor (Car 对象)
    stmt = (
        select(Task)
        .options(selectinload(Task.executor))
        .where(Task.id == task_id)
    )
    result = await db.execute(stmt)
    task = result.scalars().first()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 安全检查：任务可能还没有指派执行者
    if not task.executor:
        return {
            "task_id": task_id,
            "task_name": task.name,
            "executor": None,
            "message": "该任务目前没有关联的执行车辆"
        }
        
    return {
        "task_id": task_id,
        "task_name": task.name,
        "executor": {
            "car_id": task.executor.id,
            "car_name": task.executor.name,
            "car_status": await get_effective_car_status(
                db,
                task.executor.id,
                task.executor.status,
            ),
        }
    }
