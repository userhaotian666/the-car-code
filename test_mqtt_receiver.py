import unittest
from collections import deque
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from model import TaskStatus
from MQTT import receiver


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


class _FakeSessionContext:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _make_db(*results):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_FakeExecuteResult(item) for item in results])
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.add = Mock()
    return db


class MqttReceiverTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        receiver._recent_msg_ids.clear()
        receiver._recent_msg_queue = deque()

    async def test_process_car_data_updates_car_and_history_without_touching_task(self):
        task = SimpleNamespace(id=88, status=TaskStatus.PENDING, is_scheduled=False, finished_at=None)
        car = SimpleNamespace(id=7, ip_address="10.168.1.100", status=0, work_status=None, current_task=task)
        db = _make_db(car)
        payload = {
            "msg_id": "status-1",
            "car_ip": "10.168.1.100",
            "timestamp": 1710000000,
            "car_status": 2,
            "work_status": 5,
            "speed": 1.2,
        }

        with patch("MQTT.receiver.AsyncSessionLocal", return_value=_FakeSessionContext(db)):
            await receiver.process_car_data("car/10.168.1.100/status", payload)

        self.assertEqual(car.status, 2)
        self.assertEqual(car.work_status, 5)
        self.assertEqual(task.status, TaskStatus.PENDING)
        history = db.add.call_args.args[0]
        self.assertEqual(history.car_id, 7)
        self.assertEqual(history.car_status, 2)
        self.assertEqual(history.work_status, 5)
        db.commit.assert_awaited_once()

    async def test_process_mission_report_updates_scheduled_task_back_to_scheduled(self):
        car = SimpleNamespace(id=7, ip_address="10.168.1.100", current_task=None)
        task = SimpleNamespace(
            id=12,
            status=TaskStatus.RUNNING,
            is_scheduled=True,
            finished_at=datetime(2024, 1, 1, 0, 0, 0),
            executor=None,
        )
        db = _make_db(car, task)
        payload = {
            "msg_id": "report-1",
            "timestamp": 1710000000,
            "car_id": "car-alpha",
            "task_id": 12,
            "task_status": 0,
        }

        with patch("MQTT.receiver.AsyncSessionLocal", return_value=_FakeSessionContext(db)):
            await receiver.process_mission_report("car/10.168.1.100/task/report", payload)

        self.assertEqual(task.status, TaskStatus.SCHEDULED)
        self.assertIsNone(task.finished_at)
        db.commit.assert_awaited_once()

    async def test_process_mission_report_marks_task_completed_with_reported_time(self):
        car = SimpleNamespace(id=7, ip_address="10.168.1.100", current_task=None)
        task = SimpleNamespace(
            id=12,
            status=TaskStatus.RUNNING,
            is_scheduled=False,
            finished_at=None,
            executor=None,
        )
        db = _make_db(car, task)
        payload = {
            "msg_id": "report-2",
            "timestamp": 1710000100,
            "car_id": "car-alpha",
            "task_id": 12,
            "task_status": 2,
        }

        with patch("MQTT.receiver.AsyncSessionLocal", return_value=_FakeSessionContext(db)):
            await receiver.process_mission_report("car/10.168.1.100/task/report", payload)

        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(task.finished_at, datetime.fromtimestamp(1710000100))
        db.commit.assert_awaited_once()

    async def test_dispatch_mqtt_message_routes_by_topic(self):
        with patch("MQTT.receiver.process_car_data", new=AsyncMock()) as process_car_data, patch(
            "MQTT.receiver.process_mission_report",
            new=AsyncMock(),
        ) as process_mission_report:
            await receiver.dispatch_mqtt_message("car/10.168.1.100/status", {})
            await receiver.dispatch_mqtt_message("car/10.168.1.100/task/report", {})

        process_car_data.assert_awaited_once_with("car/10.168.1.100/status", {})
        process_mission_report.assert_awaited_once_with("car/10.168.1.100/task/report", {})


if __name__ == "__main__":
    unittest.main()
