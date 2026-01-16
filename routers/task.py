from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime
from database import get_db
from model import Task, Path, Car  # 导入你的三个模型
from schemas import TaskCreate, TaskRead# 导入上面定义的 schemas

router = APIRouter(prefix="/tasks", tags=["Tasks"])

# ================= 状态常量定义 =================
# 任务状态
TASK_UNSTARTED = 0  # 未开始
TASK_RUNNING = 1    # 进行中
TASK_PAUSED = 2     # 暂停
TASK_COMPLETED = 3  # 已完成
TASK_FAULT = 4      # 故障

# 小车状态 (沿用你提供的定义)
CAR_FAULT = 0       # 故障
CAR_STANDBY = 1     # 待机
CAR_RUNNING = 2     # 运行中

# ==========================================
# 1. 创建任务 (只创建，不分配路径和车)
# ==========================================
@router.post("/", response_model=TaskRead, status_code=status.HTTP_201_CREATED, summary="创建基础任务")
def create_task(task_in: TaskCreate, db: Session = Depends(get_db)):
    # 只需要名字和 map_id，path_id 和 executor 此时默认为 None
    db_task = Task(**task_in.model_dump())
    
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task

# 2. 绑定路径 (指定任务执行哪条路线)
# ==========================================
@router.put("/{task_id}/bind_path/{path_id}", response_model=TaskRead, summary="给任务绑定路径")
def bind_path_to_task(task_id: int, path_id: int, db: Session = Depends(get_db)):
    # 1. 获取任务
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 2. 获取路径 (验证路径是否存在)
    path = db.get(Path, path_id)
    if not path:
        raise HTTPException(status_code=404, detail="Path not found")
        
    # 3. 绑定
    task.path_id = path.id
    
    db.commit()
    db.refresh(task)
    return task

# 3. 指派车辆 (Bind Only) 
# ==========================================
@router.post("/{task_id}/assign_car/{car_id}", summary="指派车辆（仅绑定）")
def assign_car_to_task(task_id: int, car_id: int, db: Session = Depends(get_db)):
    # 1. 获取任务
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 校验：必须先绑定路径才能派车
    #if not task.path_id:
        #raise HTTPException(status_code=400, detail="Task must have a path bound first")

    # 2. 获取车辆
    car = db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    
    # 校验：车坏了不能用
    if car.status == CAR_FAULT:
         raise HTTPException(status_code=400, detail="Car is in FAULT status")
    
    # 校验：车正在跑别的任务也不能用
    if car.status == CAR_RUNNING:
        raise HTTPException(status_code=400, detail="Car is currently RUNNING another task")

    # 3. 建立关系 (只关联，不改变运行状态)
    car.current_task = task
    
    # 确保任务状态显式为“未开始” (防止它是从暂停状态切回来的)
    task.status = TASK_UNSTARTED
    
    db.commit()
    return {"message": f"Car {car.name} assigned to Task {task.name}. Ready to start.", "success": True}


# 4. 开始/继续 任务 (Start/Resume) 
# ==========================================
@router.post("/{task_id}/start", summary="开始/继续任务")
def start_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 1. 检查是否分配了车辆
    # 注意：executor 是通过 relationship 加载的 Car 对象
    if not task.executor:
        raise HTTPException(status_code=400, detail="No car assigned to this task")
    
    # 2. 检查车辆健康状况
    car = task.executor
    if car.status == CAR_FAULT:
        raise HTTPException(status_code=400, detail="Assigned car is in FAULT status")

    # 3. 修改状态
    # 任务 -> 进行中
    task.status = TASK_RUNNING
    # 小车 -> 运行中 (联动修改，体现物理世界的同步)
    car.status = CAR_RUNNING
    
    db.commit()
    return {
        "message": "Task started", 
        "task_status": task.status, 
        "car_status": car.status
    }


# 5. 暂停任务 (Pause) 
# ==========================================
@router.post("/{task_id}/pause", summary="暂停任务")
def pause_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 如果任务本来就不是运行中，暂停没有意义(或者直接返回成功)
    if task.status != TASK_RUNNING:
        return {"message": "Task is not running", "current_status": task.status}

    # 1. 修改任务状态 -> 暂停
    task.status = TASK_PAUSED
    
    # 2. 修改小车状态 -> 待机 (联动修改)
    if task.executor:
        task.executor.status = CAR_STANDBY

    db.commit()
    return {
        "message": "Task paused", 
        "task_status": task.status, 
        "car_status": task.executor.status if task.executor else None
    }

# 6. 完成任务或结束任务
@router.post("/{task_id}/finish", summary="完成任务")
def finish_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    car = task.executor

    # 1. 修改任务状态 -> 已完成
    task.status = TASK_COMPLETED
    task.finished_at = datetime.now() # 记录完成时间

    # 2. 释放车辆 (小车变回待机，且解除绑定关系)
    if car:
        car.status = CAR_STANDBY
        car.current_task_id = None # 解除绑定，让车可以接下一个任务
    
    db.commit()
    return {"message": "Task finished", "success": True}

# ================= 7. 查询任务列表 (Read List) =================
# 支持分页，支持按状态筛选
@router.get("/", response_model=List[TaskRead], summary="获取所有任务列表")
def read_tasks(
    skip: int = 0, 
    limit: int = 100, 
    status: Optional[int] = None, # 可选：按状态筛选，例如 ?status=1
    db: Session = Depends(get_db)
):
    # 1. 构建查询语句
    stmt = select(Task)
    
    # 2. 性能优化：预加载 path_info 和 executor
    # 这样 SQL 会使用 JOIN 一次性查出任务、路径和小车，避免循环查询数据库
    stmt = stmt.options(
        joinedload(Task.path_info),
        joinedload(Task.executor)
    )
    
    # 3. 如果传了 status 参数，增加过滤条件
    if status is not None:
        stmt = stmt.where(Task.status == status)
        
    # 4. 分页与排序 (按创建时间倒序)
    stmt = stmt.order_by(Task.created_at.desc()).offset(skip).limit(limit)
    
    result = db.execute(stmt)
    return result.scalars().all()

# ================= 8. 查询单个任务详情 (Read One) =================
@router.get("/{task_id}", response_model=TaskRead, summary="获取指定任务详情")
def read_task(task_id: int, db: Session = Depends(get_db)):
    # 1. 使用 select + joinedload 查询，确保关联数据也能查出来
    stmt = select(Task).options(
        joinedload(Task.path_info),
        joinedload(Task.executor)
    ).where(Task.id == task_id)
    
    result = db.execute(stmt)
    task = result.scalars().first()
    
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
        
    return task


# ================= 8. 删除任务 (Delete Task) =================
# 该接口会安全地删除任务：
# 1. 如果有车正在跑这个任务，会将车停下（状态变待机）并解绑。
# 2. 任务记录被删除。
# 3. 路径记录不受影响（保留在 paths 表中）。
@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除任务(自动释放车辆)")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    # 1. 查找任务
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 2. 处理车辆关联 (核心需求：状态变为空闲，解绑)
    car = task.executor
    if car:
        # 将车辆状态强制改为待机 (STATUS_STANDBY = 1)
        # 即使任务是暂停或运行中，任务没了，车就应该闲置
        car.status = CAR_STANDBY
        
        # 解除绑定关系
        # SQLAlchemy 会自动将 cars 表里的 current_task_id 置为 NULL
        car.current_task_id = None

    # 3. 处理路径关联
    # 任务被删除后，Task 表里的 path_id 自然消失。
    # Path 表里的记录依然存在 ("path可以保留")，符合需求。
    
    # 4. 执行删除
    db.delete(task)
    db.commit()
    
    return None