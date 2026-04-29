import unittest
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from MQTT.publisher import _build_task_command_publish_payload
from routers.command import return_to_base
from schemas import ReturnToBaseRequest


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


class _FakeDb:
    def __init__(self, car, command_id=51):
        self.car = car
        self.command_id = command_id
        self.added = None
        self.commits = 0

    async def execute(self, _stmt):
        return _FakeExecuteResult(self.car)

    def add(self, value):
        self.added = value

    async def commit(self):
        self.commits += 1

    async def refresh(self, value):
        value.id = self.command_id


def _build_car(*, car_id=7, car_ip="10.168.1.100"):
    return SimpleNamespace(id=car_id, ip_address=car_ip)


class CommandRecallPublisherTests(unittest.TestCase):
    def test_build_task_command_publish_payload_supports_numeric_recall(self):
        topic, payload, msg_id = _build_task_command_publish_payload(
            car_ip="192.168.1.20",
            task_id=51,
            task_action=0,
            recall=1,
        )

        self.assertEqual(topic, "car/192.168.1.20/task/cmd")
        self.assertTrue(msg_id.startswith("task_cmd_"))
        self.assertEqual(payload["data"]["task_id"], 51)
        self.assertEqual(payload["data"]["task_action"], 0)
        self.assertEqual(payload["data"]["recall"], 1)
        self.assertEqual(payload["data"]["all_pause"], "")


class CommandRecallRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_return_to_base_returns_404_when_car_missing(self):
        db = _FakeDb(None)

        with self.assertRaises(HTTPException) as ctx:
            await return_to_base(ReturnToBaseRequest(car_id=7), db=db)

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIsNone(db.added)

    async def test_return_to_base_requires_car_ip(self):
        db = _FakeDb(_build_car(car_ip=" "))

        with self.assertRaises(HTTPException) as ctx:
            await return_to_base(ReturnToBaseRequest(car_id=7), db=db)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("未配置 IP", ctx.exception.detail)
        self.assertIsNone(db.added)

    async def test_return_to_base_publishes_recall_command(self):
        db = _FakeDb(_build_car())

        with patch(
            "routers.command.publish_task_command_to_car",
            new=AsyncMock(return_value={"topic": "car/10.168.1.100/task/cmd", "msg_id": "msg-1"}),
        ) as publish_mock:
            result = cast(dict[str, Any], await return_to_base(ReturnToBaseRequest(car_id=7), db=db))

        self.assertEqual(result["code"], 200)
        self.assertEqual(result["data"]["command_id"], 51)
        self.assertEqual(db.added.car_id, 7)
        self.assertEqual(db.added.command_type, "RETURN_TO_BASE")
        self.assertEqual(db.added.status, 1)
        self.assertEqual(db.commits, 2)
        publish_mock.assert_awaited_once_with(
            car_ip="10.168.1.100",
            task_id=51,
            task_action=0,
            recall=1,
            all_pause="",
        )

    async def test_return_to_base_marks_command_failed_when_publish_fails(self):
        db = _FakeDb(_build_car())

        with patch(
            "routers.command.publish_task_command_to_car",
            new=AsyncMock(side_effect=RuntimeError("broker down")),
        ) as publish_mock:
            with self.assertRaises(HTTPException) as ctx:
                await return_to_base(ReturnToBaseRequest(car_id=7), db=db)

        self.assertEqual(ctx.exception.status_code, 502)
        detail = cast(dict[str, Any], ctx.exception.detail)
        self.assertEqual(detail["command_id"], 51)
        self.assertFalse(detail["mqtt_sent"])
        self.assertEqual(detail["mqtt_error"], "broker down")
        self.assertEqual(db.added.status, 3)
        self.assertIsNotNone(db.added.finished_at)
        self.assertEqual(db.commits, 2)
        publish_mock.assert_awaited_once_with(
            car_ip="10.168.1.100",
            task_id=51,
            task_action=0,
            recall=1,
            all_pause="",
        )


if __name__ == "__main__":
    unittest.main()
