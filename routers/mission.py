from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from database import get_db
from model import Car, Task, Path
from schemas import MissionCreateRequest
from sqlalchemy import select
router = APIRouter(prefix="/missions", tags=["Missions"])

STATUS_FAULT = 0   # 故障
STATUS_STANDBY = 1 # 待机 (只有它能接单)
STATUS_RUNNING = 2 # 运行

@router.post("/dispatch", summary="下发任务")
def dispatch_mission(request: MissionCreateRequest, db: Session = Depends(get_db)):
    # 1. 获取车辆
    car = db.get(Car, request.car_id)
    if not car:
        raise HTTPException(status_code=404, detail="找不到指定车辆")

    # 2. 状态检查
    if car.status == STATUS_FAULT:
        raise HTTPException(status_code=400, detail=f"车辆 {car.name} 故障(Code 0)，需维修")
    
    if car.status == STATUS_RUNNING:
        raise HTTPException(status_code=400, detail=f"车辆 {car.name} 忙碌中(Code 2)")
        
    if car.status != STATUS_STANDBY:
        raise HTTPException(status_code=400, detail=f"车辆状态异常(Code {car.status})")

    # 3. 创建路径 【这里是修改点】
    
    waypoints_data = [p.model_dump() for p in request.waypoints]
    
    # (可选) 如果需要在这里做坐标转换 (GCJ02 -> WGS84)，请在这里循环处理 waypoints_data
    
    new_path = Path(
        name=f"{request.name}_Path",
        waypoints=waypoints_data  # <--- 关键：把数据存进去！
    )
    db.add(new_path)
    db.flush() 
    # ---------------------------------------------------------

    # 4. 创建任务
    new_task = Task(
        name=request.name,
        #map_id=request.map_id,
        path_id=new_path.id,
        status=0
    )
    db.add(new_task)
    db.flush()

    # 5. 修改车辆状态
    car.current_task_id = new_task.id
    car.status = STATUS_RUNNING 
    db.add(car)

    db.commit()
    db.refresh(new_task)

    return {
        "message": "任务下发成功", 
        "data": {
            "task_id": new_task.id, 
            "car_status": 2,
            "path_points": len(waypoints_data) # 返回一下点数，方便确认
        }
    }

@router.get("/tasks/{task_id}/executor")
def get_task_executor(task_id: int, db: Session = Depends(get_db)):
    """
    获取指定任务的执行车辆信息
    """
    # 1. 查询优化：一次查询就把 Task 和 Car 都抓出来
    stmt = (
        select(Task)
        .options(joinedload(Task.executor))  # 【关键】预加载 Car 数据
        .where(Task.id == task_id)
    )
    task = db.scalar(stmt)
    
    # 2. 规范报错：使用 HTTP 404 状态码，而不是返回 200 OK 的错误字典
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
        
    if task.executor:
        return {
            "task_name": task.name,
            "car_name": task.executor.name,
            "car_id": task.executor.id,
            "car_status": task.executor.status
        }
    else:
        # 3. 语义明确：没有车时，是返回空对象还是特定消息，视前端需求而定
        return {"message": "该任务当前没有分配车辆", "car_id": None}
    

