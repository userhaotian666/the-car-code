from fastapi import APIRouter, Depends, HTTPException, status,Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select,or_,and_
from typing import List, Optional
from datetime import datetime,time

from database import get_db
from model import Task, Path, Car,TaskStatus
from schemas import TaskCreate, TaskRead

router = APIRouter(prefix="/tasks", tags=["Tasks"])


CAR_FAULT = 0
CAR_STANDBY = 1
CAR_RUNNING = 2

# 1. 创建任务 (Create Task)
# ==========================================
@router.post("/", response_model=TaskRead, status_code=status.HTTP_201_CREATED, summary="创建基础任务")
async def create_task(task_in: TaskCreate, db: AsyncSession = Depends(get_db)):
    # 1. 转换模型
    db_task = Task(**task_in.model_dump())
    
    # 2. 根据是否为定时任务，设置初始状态
    if db_task.is_scheduled:
        # 如果是定时任务 -> 状态设为 SCHEDULED (1)
        db_task.status = TaskStatus.SCHEDULED
    else:
        # 如果是普通任务 -> 状态设为 PENDING (0)
        db_task.status = TaskStatus.PENDING
        
    db.add(db_task)
    await db.commit()
    await db.refresh(db_task)
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
@router.post("/{task_id}/assign_car/{car_id}", summary="指派车辆（仅绑定）")
async def assign_car_to_task(task_id: int, car_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    car = await db.get(Car, car_id)
    
    if not task or not car:
        raise HTTPException(status_code=404, detail="任务或车辆不存在")
    
    # 车辆状态检查 (保持原逻辑)
    if car.status == CAR_FAULT:
         raise HTTPException(status_code=400, detail="车辆故障，无法指派")
    
    if car.status == CAR_RUNNING:
        raise HTTPException(status_code=400, detail="车辆正在运行中")

    # 建立关联
    car.current_task = task
    
    # 【核心逻辑修正】完全适配 TaskStatus 枚举
    if task.is_scheduled:
        # 定时任务：保持或强制设为 SCHEDULED (1)
        # 即使指派了车，它也必须等时间到了才能跑
        task.status = TaskStatus.SCHEDULED
    else:
        # 普通任务：指派了车，重置为 PENDING (0)
        # 表示"就绪"，调度器扫描到 PENDING + 有车 就会立刻改为 RUNNING
        task.status = TaskStatus.PENDING
    
    await db.commit()
    
    return {
        "message": f"车辆 {car.name} 已指派给任务 {task.name}", 
        "success": True,
        "task_status": task.status,
        "task_status_desc": task.status.name # 返回 'SCHEDULED' 或 'PENDING' 字符串给前端
    }


# ==========================================
# 4. 开始任务 (Start)
@router.post("/{task_id}/start", summary="开始/继续任务（支持强制启动定时任务）")
async def start_task(task_id: int, db: AsyncSession = Depends(get_db)):
    # 1. 查询任务并预加载执行者（小车）
    stmt = select(Task).options(selectinload(Task.executor)).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalars().first()

    # 2. 基础检查
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if not task.executor:
        raise HTTPException(status_code=400, detail="任务尚未分配车辆，无法启动")

    # 3. 状态检查逻辑优化
    # 如果任务已经是完成、取消或失败状态，不能重新开始
   # if task.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED]:
        #raise HTTPException(status_code=400, detail="任务已结束，无法重新启动")
    if task.status == TaskStatus.COMPLETED:
        task.finished_at = None
    # 如果任务已经在运行，直接返回成功（幂等性）
    if task.status == TaskStatus.RUNNING:
         return {"message": "任务已经在运行中", "task_status": task.status}

    # 4. 车辆状态检查
    # 注意：如果车辆正在运行其他任务，这里应该报错
    if task.executor.status == CAR_FAULT:
        raise HTTPException(status_code=400, detail="指派的车辆处于故障状态")
    
    # 理论上车应该是 STANDBY，或者是为了这个任务而准备的状态
    if task.executor.status == CAR_RUNNING and task.executor.current_task_id != task.id:
         raise HTTPException(status_code=400, detail="车辆正在执行其他任务")

    # 5. 核心修改：状态流转
    # ==========================================
    # 无论它是 PENDING (普通) 还是 SCHEDULED (定时) 还是 PAUSED (暂停)
    # 只要调了这个接口，就是告诉系统：现在立刻跑！
    
    task.status = TaskStatus.RUNNING
    task.executor.status = CAR_RUNNING
    
    # 可选：如果你想记录实际开始时间（而不是预计开始时间）
    # task.actual_start_at = datetime.now() 

    await db.commit()
    await db.refresh(task)
    
    return {
        "message": "任务已成功启动", 
        "task_status": task.status, 
        "is_scheduled_start": task.is_scheduled, # 告诉前端这是不是一个定时任务被启动了
        "car_status": task.executor.status
    }

# 5. 暂停任务 (Pause)
# ==========================================
@router.post("/{task_id}/pause", summary="暂停任务")
async def pause_task(task_id: int, db: AsyncSession = Depends(get_db)):
    # 1. 预加载 executor (车辆)，因为我们需要同时修改车和任务
    stmt = select(Task).options(selectinload(Task.executor)).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalars().first()

    # 2. 基础检查
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 3. 状态检查：只有 [运行中] 的任务才能暂停
    # 定时任务(SCHEDULED)还没跑，不需要暂停；已完成的任务也不能暂停
    if task.status != TaskStatus.RUNNING:
        raise HTTPException(
            status_code=400, 
            detail=f"任务当前状态为 {task.status.name}，只有 RUNNING 状态的任务可以暂停"
        )

    # 4. 修改任务状态
    task.status = TaskStatus.PAUSED

    # 5. 修改车辆状态 (关键点，见下方说明)
    if task.executor:
        # 方案 A: 如果你有 CAR_PAUSED 状态，最好用那个
        # task.executor.status = CAR_PAUSED 
        
        # 方案 B: 沿用 CAR_STANDBY，但前提是你的调度器不会把“有任务绑定但处于 STANDBY”的车分配给别人
        task.executor.status = CAR_STANDBY 
        
    await db.commit()
    await db.refresh(task)
    
    return {
        "message": "任务已暂停", 
        "task_status": task.status,
        "car_status": task.executor.status if task.executor else None
    }

# 6. 完成任务 (Finish)
# ==========================================
@router.post("/{task_id}/finish", summary="完成本次任务（不释放车辆）")
async def finish_task(task_id: int, db: AsyncSession = Depends(get_db)):
    

    # 1. 查询任务及车辆
    stmt = select(Task).options(selectinload(Task.executor)).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalars().first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 2. 更新任务状态
    # 标记为完成，表示这一轮跑完了
    task.status = TaskStatus.COMPLETED
    task.finished_at= datetime.now()

    # 3. 更新车辆状态（关键修改点）
    if task.executor:
        # 让车停下来进入待命状态
        task.executor.status = CAR_STANDBY
        
        # 【删除】不要执行下面这行，保持绑定关系！
        # task.executor.current_task_id = None 
    
    await db.commit()
    return {
        "message": "本次任务已完成，车辆保持绑定，随时可以重新开始", 
        "task_status": task.status,
        "car_status": task.executor.status if task.executor else None
    }

# 7. 查询列表 (Read List)
# ==========================================
@router.get("/", response_model=List[TaskRead], summary="获取任务列表（支持筛选）")
async def read_tasks(
    skip: int = 0, 
    limit: int = 100, 
    status: Optional[int] = Query(None, description="按状态筛选"),
    is_scheduled: Optional[bool] = Query(None, description="筛选: true=只看定时, false=只看普通, None=全部"),
    start_date: Optional[time] = Query(None, description="筛选开始时间（针对scheduled_start或created_at）"),
    end_date: Optional[time] = Query(None, description="筛选结束时间"),
    db: AsyncSession = Depends(get_db)
):
    # 1. 基础查询与预加载
    stmt = select(Task).options(
        selectinload(Task.path_info),
        selectinload(Task.executor)
    )
    
    # 2. 状态筛选
    if status is not None:
        stmt = stmt.where(Task.status == status)

    # 3. 任务类型筛选 (关键修改)
    if is_scheduled is not None:
        stmt = stmt.where(Task.is_scheduled == is_scheduled)

    # 4. 时间范围筛选
    # 逻辑：如果是定时任务，筛选 scheduled_start；否则筛选 created_at
    if start_date:
        if is_scheduled: 
            stmt = stmt.where(Task.scheduled_start >= start_date)
        else:
            stmt = stmt.where(Task.created_at >= start_date)
            
    if end_date:
        if is_scheduled:
            stmt = stmt.where(Task.scheduled_start <= end_date)
        else:
            stmt = stmt.where(Task.created_at <= end_date)

    # 5. 智能排序 (关键修改)
    if is_scheduled:
        # 定时任务：按 [预计开始时间] 正序排 (最近的先显示)
        # nulls_last 确保没有设置时间的任务排在最后
        stmt = stmt.order_by(Task.scheduled_start.asc().nulls_last())
    else:
        # 普通任务：按 [创建时间] 倒序排 (最新的先显示)
        stmt = stmt.order_by(Task.created_at.desc())

    # 6. 分页
    stmt = stmt.offset(skip).limit(limit)
    
    result = await db.execute(stmt)
    return result.scalars().all()

# 8. 查询单个任务 (Read One)
# ==========================================
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

# 9. 获取任务状态 (Get Status)
# ==========================================
@router.get("/{task_id}/status", summary="获取任务当前状态")
async def get_task_status(task_id: int, db: AsyncSession = Depends(get_db)):
    # 不需要加载其他关联，只查 Task 表，速度最快
    task = await db.get(Task, task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    return {
        "task_id": task.id, 
        "status": task.status,  # 返回枚举的整数值 (0, 1, 2...)
        # 建议加这一个字段，前端能区分是"普通未开始(0)"还是"定时未开始(1)"
        "is_scheduled": task.is_scheduled 
    }

# 10. 删除任务 (Delete)
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

# 11. 解绑车辆 (Unbind Car)
# ==========================================
@router.post("/{task_id}/unbind_car", summary="手动解绑/释放车辆")
async def unbind_car_from_task(task_id: int, db: AsyncSession = Depends(get_db)):
    # 1. 查询任务及车辆
    stmt = select(Task).options(selectinload(Task.executor)).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalars().first()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if not task.executor:
        raise HTTPException(status_code=400, detail="该任务当前没有绑定任何车辆")

    # 2. 安全检查：如果车正在跑，不能强制解绑（防止失控）
    if task.executor.status == CAR_RUNNING:
        raise HTTPException(status_code=400, detail="车辆正在运行中，请先暂停或完成任务后再解绑")

    # 3. 执行解绑
    car_name = task.executor.name
    
    # 释放车辆
    task.executor.current_task_id = None
    # 确保车辆状态为待机
    task.executor.status = CAR_STANDBY
    
    # 可选：解绑后，任务状态是否要变回 PENDING？
    # 如果解绑了车，任务就变成了“待处理且无车”的状态
    if task.status != TaskStatus.COMPLETED:
        task.status = TaskStatus.PENDING

    await db.commit()
    
    return {
        "message": f"车辆 {car_name} 已成功从任务解绑", 
        "success": True
    }