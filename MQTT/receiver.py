"""MQTT 接收端。

这个模块负责监听车端发来的 MQTT 消息，并把它们拆成两条独立的数据流：
1. `car/{car_ip}/status`：车辆基础状态与工作状态
2. `car/{car_ip}/task/report`：任务执行状态

这样可以避免把 `work_status` 错误地当成 `Task.status` 来使用。
"""

import asyncio
import json
from collections import deque
from datetime import datetime
from typing import Any

import aiomqtt
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from car_status import is_valid_car_status
from database import AsyncSessionLocal
from model import Car, CarHistory, Task, TaskStatus

from .config import (
    MAX_RECENT_MSG_IDS,
    MQTT_BROKER,
    MQTT_CLIENT_ID,
    MQTT_MISSION_REPORT_TOPIC,
    MQTT_PORT,
    MQTT_PW,
    MQTT_RECONNECT_DELAY,
    MQTT_TOPIC,
    MQTT_USER,
    SUPPORTED_VERSION,
)

# 最近处理过的消息 ID 集合，用来做 MQTT 幂等去重。
_recent_msg_ids: set[str] = set()
# 队列用来控制去重窗口大小，超过上限时淘汰最旧的 msg_id。
_recent_msg_queue: deque[str] = deque()


def _parse_int(value: Any) -> int | None:
    """尽量把外部输入转成 int，失败时返回 None。"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_float(value: Any) -> float | None:
    """尽量把外部输入转成 float，失败时返回 None。"""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_reported_at(timestamp: Any) -> datetime:
    """把车端时间戳转成 datetime；如果缺失，则退回当前时间。"""
    parsed_timestamp = _parse_int(timestamp)
    if parsed_timestamp is None:
        return datetime.now()
    return datetime.fromtimestamp(parsed_timestamp)


def _car_ip_from_topic(topic: str) -> str | None:
    """从 `car/{car_ip}/...` 形式的 topic 中提取 car_ip。"""
    parts = topic.split("/")
    if len(parts) >= 3 and parts[0] == "car":
        return parts[1]
    return None


def _remember_msg_id(msg_id: str) -> bool:
    """记录一个消息 ID，并返回它是不是第一次出现。"""
    if msg_id in _recent_msg_ids:
        return False

    _recent_msg_ids.add(msg_id)
    _recent_msg_queue.append(msg_id)

    while len(_recent_msg_queue) > MAX_RECENT_MSG_IDS:
        expired_msg_id = _recent_msg_queue.popleft()
        _recent_msg_ids.discard(expired_msg_id)

    return True


def _forget_msg_id(msg_id: str) -> None:
    """在处理失败时移除去重记录，允许后续同 msg_id 重试。"""
    _recent_msg_ids.discard(msg_id)


def _build_location(data: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """统一解析位置字段。

    兼容 `data.location`、顶层 `longitude/latitude` 以及顶层 `x/y` 写法。
    """
    location = data.get("location") or {}
    if location and not isinstance(location, dict):
        raise ValueError("location 字段不是对象，无法解析")

    return {
        "x": _parse_float(location.get("x", payload.get("longitude", payload.get("x")))),
        "y": _parse_float(location.get("y", payload.get("latitude", payload.get("y")))),
        "yaw": _parse_float(location.get("yaw", payload.get("yaw"))),
    }


def _extract_data(payload: dict[str, Any]) -> dict[str, Any]:
    """取出 MQTT 的业务体，兼容顶层字段或 `data` 包裹格式。"""
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise ValueError("消息体 data 字段不是对象，无法解析")
    return data


def _validate_payload_version(payload: dict[str, Any]) -> None:
    """校验协议版本。

    当前策略是仅打印警告，不因为版本不一致直接拒收消息。
    """
    version = str(payload.get("version") or "")
    if version and version != SUPPORTED_VERSION:
        print(f"⚠️ 收到未声明支持的协议版本: {version}")


def _normalize_status_payload(topic: str, payload: dict[str, Any]) -> dict[str, Any]:
    """把车辆状态 topic 的原始 payload 归一化成内部统一结构。"""
    topic_car_ip = _car_ip_from_topic(topic)
    payload_car_ip = payload.get("car_ip", payload.get("device_id"))
    car_ip = str(topic_car_ip or payload_car_ip or "").strip()

    if not car_ip:
        raise ValueError("消息缺少 car_ip，无法定位车辆")

    if topic_car_ip and payload_car_ip and str(topic_car_ip) != str(payload_car_ip):
        print(
            f"⚠️ topic 中的 car_ip({topic_car_ip}) 与 payload 中的 car_ip({payload_car_ip}) 不一致，优先使用 topic"
        )

    _validate_payload_version(payload)
    data = _extract_data(payload)
    location = _build_location(data, payload)

    return {
        "msg_id": str(payload.get("msg_id") or "").strip(),
        "car_ip": car_ip,
        "reported_at": _parse_reported_at(payload.get("timestamp", data.get("timestamp"))),
        "battery": _parse_int(data.get("battery", payload.get("battery"))),
        "speed": _parse_float(data.get("speed", payload.get("speed"))),
        "gear": _parse_int(data.get("gear", payload.get("gear"))),
        "mode": _parse_int(data.get("mode", payload.get("mode"))),
        "x": location["x"],
        "y": location["y"],
        "yaw": location["yaw"],
        "car_status": _parse_int(
            data.get("car_status", data.get("status", payload.get("car_status", payload.get("status"))))
        ),
        "work_status": _parse_int(data.get("work_status", payload.get("work_status"))),
    }


def _normalize_mission_report_payload(topic: str, payload: dict[str, Any]) -> dict[str, Any]:
    """把任务状态上报 topic 的原始 payload 归一化成内部统一结构。"""
    topic_car_ip = _car_ip_from_topic(topic)
    payload_car_ip = payload.get("car_ip")
    car_ip = str(topic_car_ip or payload_car_ip or "").strip()
    if not car_ip:
        raise ValueError("任务上报消息缺少 car_ip，无法定位车辆")

    _validate_payload_version(payload)
    data = _extract_data(payload)

    task_id = _parse_int(data.get("task_id", payload.get("task_id")))
    if task_id is None:
        raise ValueError("任务上报消息缺少 task_id")

    task_status = _parse_int(data.get("task_status", payload.get("task_status")))
    if task_status is None:
        raise ValueError("任务上报消息缺少 task_status")

    return {
        "msg_id": str(payload.get("msg_id") or "").strip(),
        "car_ip": car_ip,
        "reported_at": _parse_reported_at(payload.get("timestamp", data.get("timestamp"))),
        "reported_car_id": str(data.get("car_id", payload.get("car_id")) or "").strip() or None,
        "task_id": task_id,
        "task_status": task_status,
    }


def _map_reported_task_status_to_task_status(task_status: int, is_scheduled: bool) -> TaskStatus | None:
    """把车端上报的任务状态码映射成后端 TaskStatus。"""
    if task_status == 0:
        return TaskStatus.SCHEDULED if is_scheduled else TaskStatus.PENDING
    if task_status == 1:
        return TaskStatus.RUNNING
    if task_status == 2:
        return TaskStatus.COMPLETED
    return None


def _topic_kind(topic: str) -> str:
    """根据 topic 后缀判断消息属于哪条业务链路。"""
    if topic.endswith("/task/report"):
        return "mission_report"
    if topic.endswith("/status"):
        return "car_status"
    return "unknown"


async def process_car_data(topic: str, payload: dict[str, Any]) -> None:
    """处理车辆状态消息。

    这条链路只做车辆维度的事情：
    - 写 `car_history`
    - 更新 `cars.status`
    - 更新 `cars.work_status`
    """
    if not isinstance(payload, dict):
        print(f"⚠️ 忽略非 JSON 对象消息: topic={topic}")
        return

    try:
        normalized = _normalize_status_payload(topic, payload)
    except ValueError as exc:
        print(f"⚠️ MQTT 消息格式不正确: {exc}")
        return

    msg_id = normalized["msg_id"]
    if msg_id and not _remember_msg_id(msg_id):
        print(f"↩️ 忽略重复 MQTT 消息: {msg_id}")
        return

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Car).where(Car.ip_address == normalized["car_ip"])
            )
            car = result.scalars().first()

            if car is None:
                print(f"⚠️ 忽略未知车辆状态: car_ip={normalized['car_ip']}")
                _forget_msg_id(msg_id)
                return

            history = CarHistory(
                car_id=car.id,
                battery=normalized["battery"],
                speed=normalized["speed"],
                longitude=normalized["x"],
                latitude=normalized["y"],
                yaw=normalized["yaw"],
                mode=normalized["mode"],
                car_status=normalized["car_status"],
                work_status=normalized["work_status"],
                reported_at=normalized["reported_at"],
            )
            db.add(history)

            if normalized["car_status"] is not None:
                if is_valid_car_status(normalized["car_status"]):
                    car.status = int(normalized["car_status"])
                else:
                    print(
                        "⚠️ 收到非法车辆状态，忽略 cars.status 更新: "
                        f"car_ip={normalized['car_ip']}, car_id={car.id}, car_status={normalized['car_status']}"
                    )

            if normalized["work_status"] is not None:
                car.work_status = normalized["work_status"]

            await db.commit()
            print(
                "✅ 已接收车辆状态: "
                f"car_ip={normalized['car_ip']}, "
                f"car_id={car.id}, "
                f"battery={normalized['battery']}, "
                f"speed={normalized['speed']}, "
                f"gear={normalized['gear']}, "
                f"mode={normalized['mode']}, "
                f"x={normalized['x']}, "
                f"y={normalized['y']}, "
                f"yaw={normalized['yaw']}, "
                f"car_status={normalized['car_status']}, "
                f"work_status={normalized['work_status']}, "
                f"reported_at={normalized['reported_at']}"
            )
        except Exception as exc:
            await db.rollback()
            _forget_msg_id(msg_id)
            print(f"❌ MQTT 状态入库失败: {exc}")


async def process_mission_report(topic: str, payload: dict[str, Any]) -> None:
    """处理任务状态上报消息。

    这条链路专门负责更新 `tasks.status` 和 `finished_at`。
    """
    if not isinstance(payload, dict):
        print(f"⚠️ 忽略非 JSON 对象任务上报: topic={topic}")
        return

    try:
        normalized = _normalize_mission_report_payload(topic, payload)
    except ValueError as exc:
        print(f"⚠️ 任务上报消息格式不正确: {exc}")
        return

    msg_id = normalized["msg_id"]
    if msg_id and not _remember_msg_id(msg_id):
        print(f"↩️ 忽略重复任务上报消息: {msg_id}")
        return

    async with AsyncSessionLocal() as db:
        try:
            car_result = await db.execute(
                select(Car)
                .options(selectinload(Car.current_task))
                .where(Car.ip_address == normalized["car_ip"])
            )
            car = car_result.scalars().first()
            if car is None:
                print(f"⚠️ 忽略未知车辆任务上报: car_ip={normalized['car_ip']}")
                _forget_msg_id(msg_id)
                return

            task_result = await db.execute(
                select(Task)
                .options(selectinload(Task.executor))
                .where(Task.id == normalized["task_id"])
            )
            task = task_result.scalars().first()
            if task is None:
                print(
                    "⚠️ 忽略未知任务状态上报: "
                    f"car_ip={normalized['car_ip']}, task_id={normalized['task_id']}"
                )
                _forget_msg_id(msg_id)
                return

            if car.current_task and car.current_task.id != task.id:
                print(
                    "⚠️ 任务上报的 task_id 与车辆当前绑定任务不一致，仍按上报 task_id 更新: "
                    f"car_ip={normalized['car_ip']}, current_task_id={car.current_task.id}, "
                    f"reported_task_id={task.id}"
                )

            if task.executor and task.executor.id != car.id:
                print(
                    "⚠️ 任务上报车辆与任务执行车辆不一致，仍按上报 task_id 更新: "
                    f"car_ip={normalized['car_ip']}, task_id={task.id}, "
                    f"task_executor_id={task.executor.id}, reported_car_db_id={car.id}"
                )

            target_task_status = _map_reported_task_status_to_task_status(
                normalized["task_status"],
                task.is_scheduled,
            )
            if target_task_status is None:
                print(
                    "⚠️ 收到非法任务状态，忽略任务更新: "
                    f"car_ip={normalized['car_ip']}, task_id={task.id}, task_status={normalized['task_status']}"
                )
                _forget_msg_id(msg_id)
                return

            if task.status != target_task_status:
                task.status = target_task_status

            if target_task_status == TaskStatus.COMPLETED:
                task.finished_at = normalized["reported_at"]
            else:
                task.finished_at = None

            await db.commit()
            print(
                "✅ 已接收任务状态上报: "
                f"car_ip={normalized['car_ip']}, "
                f"reported_car_id={normalized['reported_car_id']}, "
                f"task_id={task.id}, "
                f"task_status={normalized['task_status']}, "
                f"mapped_task_status={task.status}, "
                f"reported_at={normalized['reported_at']}"
            )
        except Exception as exc:
            await db.rollback()
            _forget_msg_id(msg_id)
            print(f"❌ 任务状态上报处理失败: {exc}")


async def dispatch_mqtt_message(topic: str, payload: dict[str, Any]) -> None:
    """MQTT 消息分发器。

    `mqtt_listener` 只负责收消息，这个函数负责把消息转交给对应业务处理器。
    """
    kind = _topic_kind(topic)
    if kind == "car_status":
        await process_car_data(topic, payload)
        return
    if kind == "mission_report":
        await process_mission_report(topic, payload)
        return
    print(f"⚠️ 收到未识别的 MQTT topic，已忽略: {topic}")


async def mqtt_listener() -> None:
    """持续监听 MQTT 消息，断开后自动重连。

    服务启动时会把这个协程作为后台任务拉起。
    """
    while True:
        try:
            async with aiomqtt.Client(
                hostname=MQTT_BROKER,
                port=MQTT_PORT,
                username=MQTT_USER,
                password=MQTT_PW,
                identifier=MQTT_CLIENT_ID,
            ) as client:
                await client.subscribe(MQTT_TOPIC)
                await client.subscribe(MQTT_MISSION_REPORT_TOPIC)
                print(
                    "✅ MQTT 监听已启动: "
                    f"broker={MQTT_BROKER}:{MQTT_PORT}, "
                    f"status_topic={MQTT_TOPIC}, "
                    f"mission_report_topic={MQTT_MISSION_REPORT_TOPIC}, "
                    f"client_id={MQTT_CLIENT_ID}"
                )

                async for message in client.messages:
                    try:
                        payload_text = message.payload.decode("utf-8")
                        payload = json.loads(payload_text)
                        asyncio.create_task(dispatch_mqtt_message(str(message.topic), payload))
                    except json.JSONDecodeError as exc:
                        print(f"⚠️ MQTT 消息不是合法 JSON: {exc}")
                    except Exception as exc:
                        print(f"❌ MQTT 消息处理异常: {exc}")
        except asyncio.CancelledError:
            print("🛑 MQTT 监听任务收到取消信号")
            raise
        except Exception as exc:
            print(f"❌ MQTT 连接异常，{MQTT_RECONNECT_DELAY} 秒后重连: {exc}")
            await asyncio.sleep(MQTT_RECONNECT_DELAY)
