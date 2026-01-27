from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from typing import List

from database import get_db
from model import Car, Task, Path
from schemas import MissionCreateRequest

router = APIRouter(prefix="/missions", tags=["Missions"])

# 状态常量定义 (建议统一放在模型或单独的常量文件中)
STATUS_FAULT = 0   # 故障
STATUS_STANDBY = 1 # 待机
STATUS_RUNNING = 2 # 运行

# ==========================================
# 1. 任务下发 (Dispatch)
# ==========================================
@router.post("/dispatch", status_code=status.HTTP_201_CREATED, summary="下发任务并指派车辆")
async def dispatch_mission(request: MissionCreateRequest, db: AsyncSession = Depends(get_db)):
    # 1. 获取车辆并检查状态
    car = await db.get(Car, request.car_id)
    if not car:
        raise HTTPException(status_code=404, detail=f"找不到 ID 为 {request.car_id} 的车辆")

    # 逻辑校验：只有待机车辆能接单
    if car.status == STATUS_FAULT:
        raise HTTPException(status_code=400, detail="该车辆处于故障状态，无法下发任务")
    if car.status == STATUS_RUNNING:
        raise HTTPException(status_code=400, detail="该车辆正在执行其他任务，请稍后再试")

    # 2. 异步创建路径记录
    # model_dump 将 Pydantic 列表转为 Python 列表，以便存入 JSON 字段
    waypoints_data = [p.model_dump() for p in request.waypoints]
    
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
        status=0 # 初始状态：未开始
    )
    db.add(new_task)
    await db.flush() # 拿到 task.id

    # 4. 更新车辆状态并关联任务
    car.current_task_id = new_task.id
    car.status = STATUS_RUNNING 
    
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
            "car_status": task.executor.status
        }
    }