import asyncio
import json
from collections import deque
from datetime import datetime
from typing import Any

import aiomqtt
from sqlalchemy import select

from database import AsyncSessionLocal
from model import Car, CarHistory

from .config import (
    MAX_RECENT_MSG_IDS,
    MQTT_BROKER,
    MQTT_CLIENT_ID,
    MQTT_PORT,
    MQTT_PW,
    MQTT_RECONNECT_DELAY,
    MQTT_TOPIC,
    MQTT_USER,
    SUPPORTED_VERSION,
)

_recent_msg_ids: set[str] = set()
_recent_msg_queue: deque[str] = deque()


def _parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_reported_at(timestamp: Any) -> datetime:
    parsed_timestamp = _parse_int(timestamp)
    if parsed_timestamp is None:
        return datetime.now()
    return datetime.fromtimestamp(parsed_timestamp)


def _device_id_from_topic(topic: str) -> str | None:
    parts = topic.split("/")
    if len(parts) >= 3 and parts[0] == "car":
        return parts[1]
    return None


def _remember_msg_id(msg_id: str) -> bool:
    if msg_id in _recent_msg_ids:
        return False

    _recent_msg_ids.add(msg_id)
    _recent_msg_queue.append(msg_id)

    while len(_recent_msg_queue) > MAX_RECENT_MSG_IDS:
        expired_msg_id = _recent_msg_queue.popleft()
        _recent_msg_ids.discard(expired_msg_id)

    return True


def _forget_msg_id(msg_id: str) -> None:
    _recent_msg_ids.discard(msg_id)


def _normalize_payload(topic: str, payload: dict[str, Any]) -> dict[str, Any]:
    topic_device_id = _device_id_from_topic(topic)
    payload_device_id = payload.get("device_id")
    device_id = str(payload_device_id or topic_device_id or "").strip()

    if not device_id:
        raise ValueError("消息缺少 device_id，无法定位车辆")

    if topic_device_id and payload_device_id and str(topic_device_id) != str(payload_device_id):
        print(
            f"⚠️ topic 中的 device_id({topic_device_id}) 与 payload 中的 device_id({payload_device_id}) 不一致，优先使用 payload"
        )

    version = str(payload.get("version") or "")
    if version and version != SUPPORTED_VERSION:
        print(f"⚠️ 收到未声明支持的协议版本: {version}")

    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise ValueError("消息体 data 字段不是对象，无法解析")

    location = data.get("location") or {}
    if location and not isinstance(location, dict):
        raise ValueError("location 字段不是对象，无法解析")

    return {
        "msg_id": str(payload.get("msg_id") or "").strip(),
        "device_id": device_id,
        "reported_at": _parse_reported_at(payload.get("timestamp")),
        "battery": _parse_int(data.get("battery")),
        "speed": _parse_float(data.get("speed")),
        "gear": _parse_int(data.get("gear")),
        "mode": _parse_int(data.get("mode")),
        "x": _parse_float(location.get("x")),
        "y": _parse_float(location.get("y")),
        "yaw": _parse_float(location.get("yaw")),
        "car_status": _parse_int(
            data.get("car_status", data.get("status", payload.get("car_status", payload.get("status"))))
        ),
    }


async def process_car_data(topic: str, payload: dict[str, Any]) -> None:
    """处理 MQTT 状态消息并写入车辆历史表。"""
    if not isinstance(payload, dict):
        print(f"⚠️ 忽略非 JSON 对象消息: topic={topic}")
        return

    try:
        normalized = _normalize_payload(topic, payload)
    except ValueError as exc:
        print(f"⚠️ MQTT 消息格式不正确: {exc}")
        return

    msg_id = normalized["msg_id"]
    if msg_id and not _remember_msg_id(msg_id):
        print(f"↩️ 忽略重复 MQTT 消息: {msg_id}")
        return

    car_id = _parse_int(normalized["device_id"])
    if car_id is None:
        print(f"⚠️ device_id 不是有效数字，无法入库: {normalized['device_id']}")
        _forget_msg_id(msg_id)
        return

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(Car).where(Car.id == car_id))
            car = result.scalars().first()

            if car is None:
                print(f"⚠️ 忽略未知车辆状态: device_id={normalized['device_id']}")
                _forget_msg_id(msg_id)
                return

            history = CarHistory(
                car_id=car_id,
                battery=normalized["battery"],
                speed=normalized["speed"],
                longitude=normalized["x"],
                latitude=normalized["y"],
                yaw=normalized["yaw"],
                mode=normalized["mode"],
                car_status=normalized["car_status"],
                reported_at=normalized["reported_at"],
            )
            db.add(history)

            if normalized["car_status"] is not None:
                car.status = normalized["car_status"]

            await db.commit()
            print(
                "✅ 已接收车辆状态: "
                f"device_id={normalized['device_id']}, "
                f"battery={normalized['battery']}, "
                f"speed={normalized['speed']}, "
                f"gear={normalized['gear']}, "
                f"mode={normalized['mode']}, "
                f"x={normalized['x']}, "
                f"y={normalized['y']}, "
                f"yaw={normalized['yaw']}"
            )
        except Exception as exc:
            await db.rollback()
            _forget_msg_id(msg_id)
            print(f"❌ MQTT 状态入库失败: {exc}")


async def mqtt_listener() -> None:
    """持续监听 MQTT 状态消息，断开后自动重连。"""
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
                print(
                    "✅ MQTT 监听已启动: "
                    f"broker={MQTT_BROKER}:{MQTT_PORT}, "
                    f"topic={MQTT_TOPIC}, "
                    f"client_id={MQTT_CLIENT_ID}"
                )

                async for message in client.messages:
                    try:
                        payload_text = message.payload.decode("utf-8")
                        payload = json.loads(payload_text)
                        asyncio.create_task(process_car_data(str(message.topic), payload))
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
