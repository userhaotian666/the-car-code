import json
import uuid
from datetime import datetime
from typing import Any

import aiomqtt

from .config import (
    MQTT_BROKER,
    MQTT_CLIENT_ID,
    MQTT_PATH_TOPIC_TEMPLATE,
    MQTT_PORT,
    MQTT_PW,
    MQTT_USER,
    SUPPORTED_VERSION,
)


def _build_path_publish_payload(
    device_id: str,
    task_id: int,
    path_id: int,
    waypoints: list[dict[str, float]],
) -> tuple[str, dict[str, Any], str]:
    timestamp = int(datetime.now().timestamp())
    msg_id = f"path_{timestamp}_{uuid.uuid4().hex[:4]}"
    topic = MQTT_PATH_TOPIC_TEMPLATE.format(device_id=device_id)
    payload = {
        "msg_id": msg_id,
        "version": SUPPORTED_VERSION,
        "timestamp": timestamp,
        "device_id": str(device_id),
        "data": {
            "task_id": task_id,
            "path_id": path_id,
            "waypoints": waypoints,
        },
    }
    return topic, payload, msg_id


async def publish_path_to_car(
    device_id: str,
    task_id: int,
    path_id: int,
    waypoints: list[dict[str, float]],
) -> dict[str, Any]:
    """将任务路径下发给指定小车。"""
    topic, payload, msg_id = _build_path_publish_payload(device_id, task_id, path_id, waypoints)
    publisher_client_id = f"{MQTT_CLIENT_ID}_pub_{uuid.uuid4().hex[:6]}"

    async with aiomqtt.Client(
        hostname=MQTT_BROKER,
        port=MQTT_PORT,
        username=MQTT_USER,
        password=MQTT_PW,
        identifier=publisher_client_id,
    ) as client:
        await client.publish(topic, json.dumps(payload, ensure_ascii=False))

    print(
        "📤 已下发任务路径: "
        f"device_id={device_id}, "
        f"task_id={task_id}, "
        f"path_id={path_id}, "
        f"topic={topic}, "
        f"msg_id={msg_id}"
    )
    return {"topic": topic, "payload": payload, "msg_id": msg_id}
