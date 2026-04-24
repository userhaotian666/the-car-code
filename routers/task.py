from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime, time

from car_runtime import (
    get_assignment_block_reason,
    get_effective_car_status,
    get_start_block_reason,
    get_unbind_block_reason,
)
from database import get_db
from model import Task, Path, Car, TaskStatus
from schemas import TaskCreate, TaskRead
from MQTT import publish_path_to_car, publish_task_command_to_car

router = APIRouter(prefix="/tasks", tags=["Tasks"])

TASK_COMMAND_ACTION_START = 0
TASK_COMMAND_ACTION_PAUSE = 1
TASK_COMMAND_ACTION_RESUME = 2

STARTABLE_TASK_STATUSES = {
    TaskStatus.PENDING,
    TaskStatus.SCHEDULED,
    TaskStatus.COMPLETED,
}


async def _get_task_with_relations(db: AsyncSession, task_id: int) -> Optional[Task]:
    stmt = (
        select(Task)
        .options(
            selectinload(Task.path_info),
            selectinload(Task.executor).selectinload(Car.current_task),
        )
        .where(Task.id == task_id)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


def _task_status_name(task_status: int | TaskStatus) -> str:
    return task_status.name if isinstance(task_status, TaskStatus) else TaskStatus(int(task_status)).name


def _build_task_command_success_response(
    message: str,
    command_action: str,
    mqtt_result: dict,
) -> dict:
    return {
        "message": message,
        "command_action": command_action,
        "mqtt_sent": True,
        "mqtt_topic": mqtt_result["topic"],
        "mqtt_msg_id": mqtt_result["msg_id"],
        "mqtt_error": None,
    }


def _build_task_command_error_detail(
    message: str,
    command_action: str,
    mqtt_error: str,
) -> dict:
    return {
        "message": message,
        "command_action": command_action,
        "mqtt_sent": False,
        "mqtt_topic": None,
        "mqtt_msg_id": None,
        "mqtt_error": mqtt_error,
    }


def _require_task_executor(task: Optional[Task], action_text: str) -> Task:
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if not task.executor:
        raise HTTPException(status_code=400, detail=f"任务尚未分配车辆，无法{action_text}")

    car_ip = (task.executor.ip_address or "").strip()
    if not car_ip:
        raise HTTPException(status_code=400, detail=f"执行车辆未配置 IP，无法{action_text}")

    return task


async def _publish_task_command(
    task: Task,
    command_action: str,
    task_acition: int,
) -> dict:
    executor = task.executor
    if executor is None:
        raise HTTPException(status_code=400, detail="任务尚未分配车辆，无法下发任务控制命令")

    car_ip = (executor.ip_address or "").strip()
    if not car_ip:
        raise HTTPException(status_code=400, detail="执行车辆未配置 IP，无法下发任务控制命令")

    try:
        return await publish_task_command_to_car(
            car_ip=car_ip,
            task_id=task.id,
            task_acition=task_acition,
            recall="",
            all_pause="",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=_build_task_command_error_detail(
                message=f"{command_action}命令下发失败",
                command_action=command_action,
                mqtt_error=str(exc),
            ),
        ) from exc


async def _build_task_read(db: AsyncSession, task: Task) -> TaskRead:
    task_read = TaskRead.model_validate(task)
    if task_read.executor and task.executor:
        task_read.executor.status = await get_effective_car_status(
            db,
            task.executor.id,
            task.executor.status,
        )
        task_read.executor.work_status = task.executor.work_status
    return task_read


def _normalize_waypoints(raw_waypoints) -> List[list[float]]:
    if not isinstance(raw_waypoints, list) or not raw_waypoints:
        raise ValueError("路径为空，未下发 MQTT")

    normalized_waypoints: List[list[float]] = []
    for index, point in enumerate(raw_waypoints, start=1):
        if isinstance(point, (list, tuple)) and len(point) == 2:
            x, y = point
        elif isinstance(point, dict):
            x = point.get("x", point.get("lng"))
            y = point.get("y", point.get("lat"))
        else:
            raise ValueError(f"路径点 #{index} 格式不正确，未下发 MQTT")

        if x is None or y is None:
            raise ValueError(f"路径点 #{index} 缺少坐标，未下发 MQTT")

        try:
            normalized_waypoints.append([float(x), float(y)])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"路径点 #{index} 的坐标不是有效数字，未下发 MQTT") from exc

    return normalized_waypoints


def _build_mqtt_response_message(prefix: str, mqtt_result: dict) -> str:
    mqtt_state = mqtt_result["mqtt_state"]
    mqtt_error = mqtt_result["mqtt_error"]

    if mqtt_result["mqtt_sent"]:
        return f"{prefix}，路径已下发"
    if mqtt_state == "waiting_for_car":
        return f"{prefix}，待绑定车辆后自动下发"
    if mqtt_state == "waiting_for_path":
        return f"{prefix}，待绑定路径后自动下发"
    if mqtt_state == "missing_car_ip":
        return f"{prefix}，但车辆未配置 IP，无法下发 MQTT"
    if mqtt_state == "invalid_path":
        return f"{prefix}，但路径数据无效，无法下发 MQTT: {mqtt_error}"
    if mqtt_state == "publish_failed":
        return f"{prefix}，但 MQTT 下发失败: {mqtt_error}"
    return f"{prefix}，但 MQTT 未下发"


async def _maybe_publish_task_path(task: Task) -> dict:
    # 这个函数是“自动下发路径”的统一入口。
    # 任务只要同时具备两件事：
    # 1. 绑定了执行车辆
    # 2. 绑定了路径
    # 就会立刻调用这里通过 MQTT 把路径发给对应小车。
    if not task.executor:
        print(f"ℹ️ 任务待下发 MQTT，但尚未绑定车辆: task_id={task.id}")
        return {
            "mqtt_sent": False,
            "mqtt_topic": None,
            "mqtt_msg_id": None,
            "mqtt_error": None,
            "mqtt_state": "waiting_for_car",
        }

    # 下发时按车辆 IP 路由到具体小车，所以车辆没配 IP 时不能下发。
    car_ip = (task.executor.ip_address or "").strip()
    if not car_ip:
        print(
            "❌ 任务无法下发 MQTT，车辆未配置 IP: "
            f"task_id={task.id}, car_id={task.executor.id}, car_name={task.executor.name}"
        )
        return {
            "mqtt_sent": False,
            "mqtt_topic": None,
            "mqtt_msg_id": None,
            "mqtt_error": "车辆未配置 IP，无法下发 MQTT",
            "mqtt_state": "missing_car_ip",
        }

    topic = f"car/{car_ip}/task/path"
    # 如果已经有车，但路径还没绑定，就先返回“等待路径”，由后续绑定路径那一步触发自动下发。
    if not task.path_info:
        print(
            "ℹ️ 任务待下发 MQTT，但尚未绑定路径: "
            f"task_id={task.id}, car_id={task.executor.id}, car_ip={car_ip}"
        )
        return {
            "mqtt_sent": False,
            "mqtt_topic": topic,
            "mqtt_msg_id": None,
            "mqtt_error": None,
            "mqtt_state": "waiting_for_path",
        }

    try:
        # 这里把数据库里的路径点整理成 MQTT 需要的纯 x/y 数组，
        # 同时顺便挡掉空路径、脏数据、缺 x/y 的情况。
        waypoints = _normalize_waypoints(task.path_info.waypoints)
    except ValueError as exc:
        print(
            "❌ 任务无法下发 MQTT，路径数据不合法: "
            f"task_id={task.id}, car_id={task.executor.id}, car_ip={car_ip}, error={exc}"
        )
        return {
            "mqtt_sent": False,
            "mqtt_topic": topic,
            "mqtt_msg_id": None,
            "mqtt_error": str(exc),
            "mqtt_state": "invalid_path",
        }

    try:
        # 真正的 MQTT 发布在 publisher.py 里做。
        # 这里负责把任务和车辆上下文整理好，再交给发布器发往 car/{car_ip}/task/path。
        publish_result = await publish_path_to_car(
            car_ip=car_ip,
            task_id=task.id,
            is_scheduled=task.is_scheduled,
            scheduled_start=task.scheduled_start,
            scheduled_end=task.scheduled_end,
            waypoints=waypoints,
        )
    except Exception as exc:
        print(
            "❌ 任务路径 MQTT 下发失败: "
            f"task_id={task.id}, car_id={task.executor.id}, car_ip={car_ip}, path_id={task.path_info.id}, error={exc}"
        )
        return {
            "mqtt_sent": False,
            "mqtt_topic": topic,
            "mqtt_msg_id": None,
            "mqtt_error": f"路径下发失败: {exc}",
            "mqtt_state": "publish_failed",
        }

    # start 接口不重复下发路径，目的是避免同一条任务因为“绑定完成”和“开始任务”各发一遍。
    # 所以只要这里已经成功发过，后续任务启动就直接复用小车本地已收到的路径。
    return {
        "mqtt_sent": True,
        "mqtt_topic": publish_result["topic"],
        "mqtt_msg_id": publish_result["msg_id"],
        "mqtt_error": None,
        "mqtt_state": "sent",
    }

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
@router.put("/{task_id}/bind_path/{path_id}", summary="给任务绑定路径")
async def bind_path_to_task(task_id: int, path_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    path = await db.get(Path, path_id)
    if not path:
        raise HTTPException(status_code=404, detail="Path not found")
        
    task.path_id = path.id
    await db.commit()
    task_with_relations = await _get_task_with_relations(db, task_id)
    if not task_with_relations:
        raise HTTPException(status_code=404, detail="Task not found")

    mqtt_result = await _maybe_publish_task_path(task_with_relations)
    message = _build_mqtt_response_message("路径已绑定", mqtt_result)

    return {
        "message": message,
        "success": True,
        "task_id": task_with_relations.id,
        "path_id": task_with_relations.path_id,
        "car_id": task_with_relations.executor.id if task_with_relations.executor else None,
        "mqtt_sent": mqtt_result["mqtt_sent"],
        "mqtt_topic": mqtt_result["mqtt_topic"],
        "mqtt_msg_id": mqtt_result["mqtt_msg_id"],
        "mqtt_error": mqtt_result["mqtt_error"],
        "mqtt_state": mqtt_result["mqtt_state"],
    }

# ==========================================
# 3. 指派车辆 (Assign Car)
@router.post("/{task_id}/assign_car/{car_id}", summary="指派车辆（仅绑定）")
async def assign_car_to_task(task_id: int, car_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    stmt = (
        select(Car)
        .options(selectinload(Car.current_task))
        .where(Car.id == car_id)
    )
    result = await db.execute(stmt)
    car = result.scalars().first()
    
    if not task or not car:
        raise HTTPException(status_code=404, detail="任务或车辆不存在")
    
    block_reason = get_assignment_block_reason(car)
    if block_reason:
        raise HTTPException(status_code=400, detail=block_reason)

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
    task_with_relations = await _get_task_with_relations(db, task_id)
    if not task_with_relations:
        raise HTTPException(status_code=404, detail="任务不存在")

    mqtt_result = await _maybe_publish_task_path(task_with_relations)
    message = _build_mqtt_response_message(
        f"车辆 {car.name} 已指派给任务 {task.name}",
        mqtt_result,
    )
    
    return {
        "message": message, 
        "success": True,
        "task_status": task_with_relations.status,
        "task_status_desc": task_with_relations.status.name, # 返回 'SCHEDULED' 或 'PENDING' 字符串给前端
        "task_id": task_with_relations.id,
        "path_id": task_with_relations.path_id,
        "car_id": task_with_relations.executor.id if task_with_relations.executor else None,
        "mqtt_sent": mqtt_result["mqtt_sent"],
        "mqtt_topic": mqtt_result["mqtt_topic"],
        "mqtt_msg_id": mqtt_result["mqtt_msg_id"],
        "mqtt_error": mqtt_result["mqtt_error"],
        "mqtt_state": mqtt_result["mqtt_state"],
    }


# ==========================================
# 4. 开始任务 (Start)
@router.post("/{task_id}/start", summary="开始任务")
async def start_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = _require_task_executor(await _get_task_with_relations(db, task_id), "启动")

    if task.status not in STARTABLE_TASK_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"任务当前状态为 {_task_status_name(task.status)}，无法开始任务",
        )

    block_reason = get_start_block_reason(task.executor, task.id)
    if block_reason:
        raise HTTPException(status_code=400, detail=block_reason)

    mqtt_result = await _publish_task_command(
        task=task,
        command_action="start",
        task_acition=TASK_COMMAND_ACTION_START,
    )

    return _build_task_command_success_response(
        message="开始任务命令已下发",
        command_action="start",
        mqtt_result=mqtt_result,
    )

# 5. 暂停任务 (Pause)
# ==========================================
@router.post("/{task_id}/pause", summary="暂停任务")
async def pause_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = _require_task_executor(await _get_task_with_relations(db, task_id), "暂停")


    if task.status != TaskStatus.RUNNING:
        raise HTTPException(
            status_code=400,
            detail=f"任务当前状态为 {_task_status_name(task.status)}，只有 RUNNING 状态的任务可以暂停",
        )


    mqtt_result = await _publish_task_command(
        task=task,
        command_action="pause",
        task_acition=TASK_COMMAND_ACTION_PAUSE,
    )

    return _build_task_command_success_response(
        message="暂停任务命令已下发",
        command_action="pause",
        mqtt_result=mqtt_result,
    )


# 6. 继续任务 (Resume)
# ==========================================
@router.post("/{task_id}/resume", summary="继续任务")
async def resume_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = _require_task_executor(await _get_task_with_relations(db, task_id), "继续")

    if task.status != TaskStatus.PAUSED:
        raise HTTPException(
            status_code=400,
            detail=f"任务当前状态为 {_task_status_name(task.status)}，只有 PAUSED 状态的任务可以继续",
        )

    mqtt_result = await _publish_task_command(
        task=task,
        command_action="resume",
        task_acition=TASK_COMMAND_ACTION_RESUME,
    )

    return _build_task_command_success_response(
        message="继续任务命令已下发",
        command_action="resume",
        mqtt_result=mqtt_result,
    )

# 7. 完成任务 (Finish)
# ==========================================
@router.post("/{task_id}/finish", summary="完成本次任务（不释放车辆）")
async def finish_task(task_id: int, db: AsyncSession = Depends(get_db)):
    

    # 1. 查询任务及车辆
    stmt = (
        select(Task)
        .options(selectinload(Task.executor).selectinload(Car.current_task))
        .where(Task.id == task_id)
    )
    result = await db.execute(stmt)
    task = result.scalars().first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 2. 更新任务状态
    # 标记为完成，表示这一轮跑完了
    task.status = TaskStatus.COMPLETED
    task.finished_at= datetime.now()
    
    await db.commit()
    return {
        "message": "本次任务已完成，车辆保持绑定，随时可以重新开始", 
        "task_status": task.status,
        "car_status": task.executor.status if task.executor else None
    }

# 8. 查询列表 (Read List)
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

# 9. 查询单个任务 (Read One)
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
    return await _build_task_read(db, task)

# 10. 获取任务状态 (Get Status)
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

# 11. 删除任务 (Delete)
# ==========================================
@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除任务并释放资源")
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Task)
        .options(selectinload(Task.executor).selectinload(Car.current_task))
        .where(Task.id == task_id)
    )
    result = await db.execute(stmt)
    task = result.scalars().first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.executor:
        block_reason = get_unbind_block_reason(task.executor, task.id)
        if block_reason:
            raise HTTPException(status_code=400, detail=block_reason)
        task.executor.current_task_id = None

    await db.delete(task)
    await db.commit()
    return None

# 12. 解绑车辆 (Unbind Car)
# ==========================================
@router.post("/{task_id}/unbind_car", summary="手动解绑/释放车辆")
async def unbind_car_from_task(task_id: int, db: AsyncSession = Depends(get_db)):
    # 1. 查询任务及车辆
    stmt = (
        select(Task)
        .options(selectinload(Task.executor).selectinload(Car.current_task))
        .where(Task.id == task_id)
    )
    result = await db.execute(stmt)
    task = result.scalars().first()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if not task.executor:
        raise HTTPException(status_code=400, detail="该任务当前没有绑定任何车辆")

    # 2. 安全检查：只有待机中的车辆才能解绑
    block_reason = get_unbind_block_reason(task.executor, task.id)
    if block_reason:
        raise HTTPException(status_code=400, detail=block_reason)

    # 3. 执行解绑
    car_name = task.executor.name
    
    # 释放车辆
    task.executor.current_task_id = None
    
    # 可选：解绑后，任务状态是否要变回 PENDING？
    # 如果解绑了车，任务就变成了“待处理且无车”的状态
    if task.status != TaskStatus.COMPLETED:
        task.status = TaskStatus.PENDING

    await db.commit()
    
    return {
        "message": f"车辆 {car_name} 已成功从任务解绑", 
        "success": True
    }
