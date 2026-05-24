import asyncio
from datetime import datetime
from typing import Any

from fastapi import WebSocket

Point = list[float]

# 这里不入库，专门保存“当前后端进程正在运行期间”的小车规划路径。
# key 是 task_id；value 里保存这个任务已收到的分段、合并后的最新状态等。
_live_paths: dict[int, dict[str, Any]] = {}

# 每个 task_id 可以被多个前端页面同时订阅，收到新分段时会广播给这些连接。
_subscribers: dict[int, set[WebSocket]] = {}

# MQTT 接收和 WebSocket 订阅都在 asyncio 事件循环里运行，用锁避免同时改内存字典。
_lock = asyncio.Lock()


def _now_iso() -> str:
    return datetime.now().isoformat()


def _build_snapshot(task_id: int) -> dict[str, Any]:
    """构造给前端的完整快照。

    WebSocket 刚连接时会先发一份 snapshot；后续 MQTT 新分段到达时再发 update。
    """
    state = _live_paths.get(task_id)
    if not state:
        # 前端可能先打开页面、后收到车端路径，所以这里返回一个空路径快照。
        return {
            "type": "live_path_snapshot",
            "task_id": task_id,
            "car_ip": None,
            "segment_index": None,
            "is_last": False,
            "points": [],
            "full_points": [],
            "updated_at": None,
        }

    full_points: list[Point] = []
    segments: dict[int, list[Point]] = state["segments"]
    # 分段可能乱序到达，所以每次按 segment_index 排序后再拼成完整路径。
    for segment_index in sorted(segments):
        full_points.extend(segments[segment_index])

    return {
        "type": "live_path_snapshot",
        "task_id": task_id,
        "car_ip": state["car_ip"],
        "segment_index": state["last_segment_index"],
        "is_last": state["is_complete"],
        "points": state["last_points"],
        "full_points": full_points,
        "updated_at": state["updated_at"],
    }


async def get_live_path_snapshot(task_id: int) -> dict[str, Any]:
    """读取某个任务当前缓存的 live path，用于 WebSocket 初始推送。"""
    async with _lock:
        return _build_snapshot(task_id)


async def subscribe_live_path(task_id: int, websocket: WebSocket) -> None:
    """注册一个前端 WebSocket 连接，让它接收指定任务的 live path 更新。"""
    async with _lock:
        _subscribers.setdefault(task_id, set()).add(websocket)


async def unsubscribe_live_path(task_id: int, websocket: WebSocket) -> None:
    """移除已经断开的 WebSocket 连接，避免后续广播继续写入失效连接。"""
    async with _lock:
        subscribers = _subscribers.get(task_id)
        if not subscribers:
            return
        subscribers.discard(websocket)
        if not subscribers:
            _subscribers.pop(task_id, None)


async def _broadcast_live_path(task_id: int, message: dict[str, Any]) -> None:
    """把 live path 更新广播给订阅同一个 task_id 的所有前端。"""
    async with _lock:
        # 复制一份连接列表后再发消息，避免发送过程中长时间占用锁。
        subscribers = list(_subscribers.get(task_id, set()))

    stale_connections: list[WebSocket] = []
    for websocket in subscribers:
        try:
            await websocket.send_json(message)
        except Exception:
            stale_connections.append(websocket)

    if stale_connections:
        async with _lock:
            current_subscribers = _subscribers.get(task_id)
            if current_subscribers:
                # 发送失败通常说明前端已经断开，这里顺手清理掉。
                for websocket in stale_connections:
                    current_subscribers.discard(websocket)
                if not current_subscribers:
                    _subscribers.pop(task_id, None)


async def update_live_path_segment(
    *,
    task_id: int,
    car_ip: str,
    segment_index: int,
    is_last: bool,
    points: list[Point],
) -> tuple[dict[str, Any], bool]:
    """写入一个 live path 分段，并返回给前端的更新消息。

    返回值第二项表示这次是否真的写入了新分段；如果是重复 segment_index，
    会返回 False，调用方可以据此忽略重复 MQTT 消息。
    """
    async with _lock:
        existing_state = _live_paths.get(task_id)

        # 一条任务完成后，如果小车又从 segment_index=0 开始上报，认为是新一轮规划。
        # 这样可以复用同一个 task_id 重新开始任务，而不会混进上一次的路径。
        if segment_index == 0 and (not existing_state or existing_state["is_complete"]):
            existing_state = None

        if existing_state is None:
            # segments 保存原始分段，full_points 每次按 segment_index 临时拼出来。
            existing_state = {
                "task_id": task_id,
                "car_ip": car_ip,
                "segments": {},
                "is_complete": False,
                "last_segment_index": None,
                "last_points": [],
                "updated_at": None,
            }
            _live_paths[task_id] = existing_state

        segments: dict[int, list[Point]] = existing_state["segments"]
        if segment_index in segments:
            # MQTT 可能重发同一个分段，避免把同一段点重复追加到前端路径里。
            return _build_snapshot(task_id), False

        segments[segment_index] = points
        existing_state["car_ip"] = car_ip
        existing_state["last_segment_index"] = segment_index
        existing_state["last_points"] = points
        existing_state["is_complete"] = bool(is_last)
        existing_state["updated_at"] = _now_iso()

        snapshot = _build_snapshot(task_id)
        update_message = {
            **snapshot,
            "type": "live_path_update",
            # update 的 points 表示本次新增分段，full_points 表示当前完整规划路径。
            "is_last": bool(is_last),
            "points": points,
        }

    await _broadcast_live_path(task_id, update_message)
    return update_message, True


async def reset_live_path_state() -> None:
    """测试辅助函数：清空内存缓存和订阅者。"""
    async with _lock:
        _live_paths.clear()
        _subscribers.clear()
