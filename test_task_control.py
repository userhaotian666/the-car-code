import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from MQTT.publisher import _build_task_command_publish_payload
from model import TaskStatus
from routers.task import pause_task, resume_task, start_task


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def first(self):
        return self._value


class _FakeExecuteResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return _FakeScalarResult(self._value)


def _build_db(task):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_FakeExecuteResult(task))
    return db


def _build_task(
    *,
    task_id=1,
    status=TaskStatus.PENDING,
    has_executor=True,
    car_ip="10.168.1.100",
):
    executor = None
    if has_executor:
        executor = SimpleNamespace(
            id=101,
            name="Car-101",
            ip_address=car_ip,
            current_task_id=task_id,
            current_task=None,
            status=0,
        )

    task = SimpleNamespace(
        id=task_id,
        name=f"task-{task_id}",
        status=status,
        executor=executor,
        is_scheduled=False,
    )
    if executor is not None:
        executor.current_task = task
    return task


class TaskCommandPublisherTests(unittest.TestCase):
    def test_build_task_command_publish_payload(self):
        topic, payload, msg_id = _build_task_command_publish_payload(
            car_ip="192.168.1.20",
            task_id=12,
            task_acition=2,
        )

        self.assertEqual(topic, "car/192.168.1.20/task/cmd")
        self.assertTrue(msg_id.startswith("task_cmd_"))
        self.assertEqual(payload["car_ip"], "192.168.1.20")
        self.assertIsInstance(payload["timestamp"], int)
        self.assertEqual(payload["data"]["task_id"], 12)
        self.assertEqual(payload["data"]["task_acition"], 2)
        self.assertEqual(payload["data"]["recall"], "")
        self.assertEqual(payload["data"]["all_pause"], "")


class TaskControlRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_task_returns_404_when_missing(self):
        db = _build_db(None)

        with self.assertRaises(HTTPException) as ctx:
            await start_task(1, db=db)

        self.assertEqual(ctx.exception.status_code, 404)

    async def test_start_task_requires_executor(self):
        db = _build_db(_build_task(has_executor=False))

        with self.assertRaises(HTTPException) as ctx:
            await start_task(1, db=db)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("任务尚未分配车辆", ctx.exception.detail)

    async def test_start_task_requires_car_ip(self):
        db = _build_db(_build_task(car_ip=" "))

        with self.assertRaises(HTTPException) as ctx:
            await start_task(1, db=db)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("未配置 IP", ctx.exception.detail)

    async def test_pause_task_requires_running_status(self):
        db = _build_db(_build_task(status=TaskStatus.PENDING))

        with self.assertRaises(HTTPException) as ctx:
            await pause_task(1, db=db)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("只有 RUNNING 状态的任务可以暂停", ctx.exception.detail)

    async def test_resume_task_requires_paused_status(self):
        db = _build_db(_build_task(status=TaskStatus.RUNNING))

        with self.assertRaises(HTTPException) as ctx:
            await resume_task(1, db=db)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("只有 PAUSED 状态的任务可以继续", ctx.exception.detail)

    async def test_start_task_publishes_mqtt_command(self):
        db = _build_db(_build_task(status=TaskStatus.PENDING))

        with patch("routers.task.get_start_block_reason", return_value=None), patch(
            "routers.task.publish_task_command_to_car",
            new=AsyncMock(return_value={"topic": "car/10.168.1.100/task/cmd", "msg_id": "msg-1"}),
        ) as publish_mock:
            result = await start_task(1, db=db)

        self.assertTrue(result["mqtt_sent"])
        self.assertEqual(result["command_action"], "start")
        self.assertEqual(result["mqtt_topic"], "car/10.168.1.100/task/cmd")
        publish_mock.assert_awaited_once_with(
            car_ip="10.168.1.100",
            task_id=1,
            task_acition=0,
            recall="",
            all_pause="",
        )

    async def test_pause_task_publishes_mqtt_command(self):
        db = _build_db(_build_task(status=TaskStatus.RUNNING))

        with patch(
            "routers.task.publish_task_command_to_car",
            new=AsyncMock(return_value={"topic": "car/10.168.1.100/task/cmd", "msg_id": "msg-2"}),
        ) as publish_mock:
            result = await pause_task(1, db=db)

        self.assertTrue(result["mqtt_sent"])
        self.assertEqual(result["command_action"], "pause")
        publish_mock.assert_awaited_once_with(
            car_ip="10.168.1.100",
            task_id=1,
            task_acition=1,
            recall="",
            all_pause="",
        )

    async def test_resume_task_publishes_mqtt_command(self):
        db = _build_db(_build_task(status=TaskStatus.PAUSED))

        with patch(
            "routers.task.publish_task_command_to_car",
            new=AsyncMock(return_value={"topic": "car/10.168.1.100/task/cmd", "msg_id": "msg-3"}),
        ) as publish_mock:
            result = await resume_task(1, db=db)

        self.assertTrue(result["mqtt_sent"])
        self.assertEqual(result["command_action"], "resume")
        publish_mock.assert_awaited_once_with(
            car_ip="10.168.1.100",
            task_id=1,
            task_acition=2,
            recall="",
            all_pause="",
        )

    async def test_start_task_returns_clear_error_when_publish_fails(self):
        db = _build_db(_build_task(status=TaskStatus.PENDING))

        with patch("routers.task.get_start_block_reason", return_value=None), patch(
            "routers.task.publish_task_command_to_car",
            new=AsyncMock(side_effect=RuntimeError("broker down")),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await start_task(1, db=db)

        self.assertEqual(ctx.exception.status_code, 502)
        self.assertEqual(ctx.exception.detail["command_action"], "start")
        self.assertFalse(ctx.exception.detail["mqtt_sent"])
        self.assertEqual(ctx.exception.detail["mqtt_error"], "broker down")


if __name__ == "__main__":
    unittest.main()
