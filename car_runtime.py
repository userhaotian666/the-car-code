"""车辆运行时规则工具。

这个模块不直接操作数据库，而是封装“车辆当前能不能做某件事”的规则判断，
供任务路由、调度器等地方复用。
"""

from typing import Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from CRUD import get_latest_car_status_async
from car_status import CarStatus, get_car_status_label, normalize_car_status
from model import TaskStatus

# 任务已经结束的状态集合。只要任务落在这里，就不再算“活跃任务”。
TERMINAL_TASK_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
}


class TaskLike(Protocol):
    """任务协议类型。

    只声明本模块实际会访问到的字段，方便类型检查器理解“传进来的任务至少要有什么”。
    """
    status: int | TaskStatus


class CarLike(Protocol):
    """车辆协议类型。

    同样只声明本模块关心的字段，避免因为 ORM / mock / 简单对象的差异导致 IDE 报错。
    """
    status: int
    current_task_id: Optional[int]
    current_task: Optional[TaskLike]


def _normalize_task_status(value: int | TaskStatus) -> TaskStatus:
    """把 int 或 TaskStatus 统一收敛成 TaskStatus。"""
    return value if isinstance(value, TaskStatus) else TaskStatus(int(value))


def task_is_active(task: TaskLike | None) -> bool:
    """判断任务是否仍然处于“活跃中”。"""
    if task is None:
        return False
    return _normalize_task_status(task.status) not in TERMINAL_TASK_STATUSES


def car_has_other_active_task(car: CarLike, current_task_id: Optional[int] = None) -> bool:
    """判断车辆是否已经被别的未结束任务占用。"""
    if car.current_task_id is None:
        return False

    if current_task_id is not None and car.current_task_id == current_task_id:
        return False

    if car.current_task is None:
        return True

    return task_is_active(car.current_task)


def _build_status_message(status: object, action: str) -> str:
    """生成统一的车辆状态阻塞提示文案。"""
    label = get_car_status_label(status)
    return f"车辆当前为{label}，无法{action}"


def get_assignment_block_reason(car: CarLike) -> Optional[str]:
    """判断车辆是否允许被指派任务。

    返回：
    - None：允许指派
    - str：阻塞原因
    """
    status = normalize_car_status(car.status)
    if status is None:
        return _build_status_message(car.status, "指派")

    if status != CarStatus.STANDBY.value:
        return _build_status_message(status, "指派")

    if car_has_other_active_task(car):
        return "车辆已绑定其他未结束任务，无法指派"

    return None


def get_start_block_reason(car: CarLike, current_task_id: int) -> Optional[str]:
    """判断车辆是否允许启动指定任务。"""
    status = normalize_car_status(car.status)
    if status is None:
        return _build_status_message(car.status, "启动任务")

    if status in {
        CarStatus.CHARGING.value,
        CarStatus.RETURNING.value,
        CarStatus.ERROR.value,
    }:
        return _build_status_message(status, "启动任务")

    if car_has_other_active_task(car, current_task_id=current_task_id):
        return "车辆已被其他未结束任务占用，无法启动当前任务"

    return None


def get_unbind_block_reason(car: CarLike, current_task_id: int) -> Optional[str]:
    """判断车辆是否允许从当前任务解绑。"""
    if car_has_other_active_task(car, current_task_id=current_task_id):
        return "车辆已被其他未结束任务占用，无法解绑当前任务"

    status = normalize_car_status(car.status)
    if status is None:
        return _build_status_message(car.status, "解绑")

    if status != CarStatus.STANDBY.value:
        return _build_status_message(status, "解绑")

    return None


async def get_effective_car_status(
    db: AsyncSession,
    car_id: int,
    fallback_status: Optional[int],
) -> int:
    """获取车辆“当前最可信”的状态。

    优先级：
    1. 最新一条 `car_history.car_status`
    2. `cars.status` 作为 fallback
    3. 如果两者都不可用，则返回 STANDBY
    """
    latest_history = await get_latest_car_status_async(db, car_id)
    if latest_history:
        latest_status = normalize_car_status(latest_history.car_status)
        if latest_status is not None:
            return latest_status
    if fallback_status is not None:
        fallback = normalize_car_status(fallback_status)
        if fallback is not None:
            return fallback
    return CarStatus.STANDBY.value
