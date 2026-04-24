"""MQTT 发布端。

这个模块负责把后端要发给小车的命令统一组包并发布出去。
目前包含两类发送能力：
1. 路径下发：`car/{car_ip}/task/path`
2. 任务控制命令：`car/{car_ip}/task/cmd`
"""

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
    MQTT_TASK_CMD_TOPIC_TEMPLATE,
    MQTT_USER,
    SUPPORTED_VERSION,
)


def _build_path_publish_payload(
    car_ip: str,
    task_id: int,
    is_scheduled: bool,
    scheduled_start: Any,
    scheduled_end: Any,
    waypoints: list[list[float]],
) -> tuple[str, dict[str, Any], str]:
    """构造“路径下发”消息。

    这里只负责组织 topic / payload / msg_id，
    不负责真正连 broker 发送网络请求。
    """
    timestamp = int(datetime.now().timestamp())
    msg_id = f"path_{timestamp}_{uuid.uuid4().hex[:4]}"

    # 路径下发固定发到每辆车自己的路径 topic。
    topic = MQTT_PATH_TOPIC_TEMPLATE.format(car_ip=car_ip, device_id=car_ip)
    payload = {
        "msg_id": msg_id,
        "version": SUPPORTED_VERSION,
        "timestamp": timestamp,
        "car_ip": str(car_ip),
        "data": {
            "task_id": task_id,
            "is_scheduled": is_scheduled,
            "scheduled_start": scheduled_start.isoformat() if scheduled_start else None,
            "scheduled_end": scheduled_end.isoformat() if scheduled_end else None,
            # way_points 保持前端点击路径时的原始顺序，车端按收到的顺序逐点执行即可。
            "way_points": waypoints,
        },
    }
    return topic, payload, msg_id


def _build_task_command_publish_payload(
    car_ip: str,
    task_id: int,
    task_acition: int,
    recall: str = "",
    all_pause: str = "",
) -> tuple[str, dict[str, Any], str]:
    """构造“任务控制命令”消息。

    `task_acition` 是车端协议里的原始字段名，这里保持不改，
    避免后端和小车协议字段不一致。
    """
    timestamp = int(datetime.now().timestamp())
    msg_id = f"task_cmd_{timestamp}_{uuid.uuid4().hex[:4]}"
    topic = MQTT_TASK_CMD_TOPIC_TEMPLATE.format(car_ip=car_ip, device_id=car_ip)
    payload = {
        "msg_id": msg_id,
        "version": SUPPORTED_VERSION,
        "timestamp": timestamp,
        "car_ip": str(car_ip),
        "data": {
            "task_id": task_id,
            "task_acition": task_acition,
            "recall": recall,
            "all_pause": all_pause,
        },
    }
    return topic, payload, msg_id


async def _publish_payload(topic: str, payload: dict[str, Any]) -> None:
    """把已经组好的 payload 发布到指定 topic。"""
    # 发布端每次单独生成一个 client_id，避免和接收端抢占同一个连接。
    publisher_client_id = f"{MQTT_CLIENT_ID}_pub_{uuid.uuid4().hex[:6]}"

    async with aiomqtt.Client(
        hostname=MQTT_BROKER,
        port=MQTT_PORT,
        username=MQTT_USER,
        password=MQTT_PW,
        identifier=publisher_client_id,
    ) as client:
        await client.publish(topic, json.dumps(payload, ensure_ascii=False))


async def publish_path_to_car(
    car_ip: str,
    task_id: int,
    is_scheduled: bool,
    scheduled_start: Any,
    scheduled_end: Any,
    waypoints: list[list[float]],
) -> dict[str, Any]:
    """将任务路径下发给指定小车。

    返回值里会把 topic / payload / msg_id 带回去，
    这样路由层可以直接把这些信息返回给前端或写日志。
    """
    topic, payload, msg_id = _build_path_publish_payload(
        car_ip,
        task_id,
        is_scheduled,
        scheduled_start,
        scheduled_end,
        waypoints,
    )

    # 当前采用“只管发，不等 ACK”的模式：broker 接收成功就认为下发完成。
    await _publish_payload(topic, payload)

    print(
        "📤 已下发任务路径: "
        f"car_ip={car_ip}, "
        f"task_id={task_id}, "
        f"topic={topic}, "
        f"msg_id={msg_id}"
    )
    return {"topic": topic, "payload": payload, "msg_id": msg_id}


async def publish_task_command_to_car(
    car_ip: str,
    task_id: int,
    task_acition: int,
    recall: str = "",
    all_pause: str = "",
) -> dict[str, Any]:
    """向指定小车下发任务控制命令。

    适用于开始、暂停、继续任务等动作。
    """
    topic, payload, msg_id = _build_task_command_publish_payload(
        car_ip=car_ip,
        task_id=task_id,
        task_acition=task_acition,
        recall=recall,
        all_pause=all_pause,
    )

    await _publish_payload(topic, payload)

    print(
        "📤 已下发任务控制命令: "
        f"car_ip={car_ip}, "
        f"task_id={task_id}, "
        f"task_acition={task_acition}, "
        f"topic={topic}, "
        f"msg_id={msg_id}"
    )
    return {"topic": topic, "payload": payload, "msg_id": msg_id}
