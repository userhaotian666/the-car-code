"""车辆状态定义与辅助工具。

这个模块解决两类问题：
1. 给车辆状态码一个统一的枚举和中文标签
2. 提供“状态归一化 / 校验 / 文案显示”的公共函数
"""

from enum import IntEnum
from typing import Any, Final


class CarStatus(IntEnum):
    """车辆基础状态枚举。

    这里表达的是车辆整体所处的业务状态，不是任务状态，也不是 work_status。
    """
    STANDBY = 0
    CHARGING = 1
    EXECUTING = 2
    RETURNING = 3
    ERROR = 4

# 状态码到中文文案的映射，主要用于接口返回和错误提示。
CAR_STATUS_LABELS: Final[dict[int, str]] = {
    CarStatus.STANDBY.value: "待机",
    CarStatus.CHARGING.value: "充电执行中",
    CarStatus.EXECUTING.value: "任务执行中",
    CarStatus.RETURNING.value: "任务完成返回中",
    CarStatus.ERROR.value: "异常状态",
}
# 所有合法车辆状态码的集合，便于做快速校验。
VALID_CAR_STATUSES: Final[set[int]] = {status.value for status in CarStatus}


def normalize_car_status(value: Any) -> int | None:
    """把任意输入尽量转成合法车辆状态码。

    返回：
    - 合法状态码：对应的 int
    - 非法或无法转换：None
    """
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized in VALID_CAR_STATUSES else None


def get_car_status_label(value: Any) -> str:
    """把状态码转成人能读懂的中文文案。"""
    normalized = normalize_car_status(value)
    if normalized is None:
        return f"未知状态({value})"
    return CAR_STATUS_LABELS[normalized]


def is_valid_car_status(value: Any) -> bool:
    """判断一个值能否被视为合法车辆状态码。"""
    return normalize_car_status(value) is not None
