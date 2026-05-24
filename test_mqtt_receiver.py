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


def _build_mission_report_payload(msg_id: str, task_status: int, timestamp: int = 1710000000):
    return {
        "msg_id": msg_id,
        "timestamp": timestamp,
        "car_id": "car-alpha",
        "task_id": 12,
        "task_status": task_status,
    }


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

    async def _assert_mission_report_status(
        self,
        reported_status: int,
        expected_status: TaskStatus,
        *,
        is_scheduled: bool = False,
        initial_finished_at: datetime | None = datetime(2024, 1, 1, 0, 0, 0),
        expected_finished_at: datetime | None = None,
        msg_id: str | None = None,
        timestamp: int = 1710000000,
    ):
        car = SimpleNamespace(id=7, ip_address="10.168.1.100", current_task=None)
        task = SimpleNamespace(
            id=12,
            status=TaskStatus.RUNNING,
            is_scheduled=is_scheduled,
            finished_at=initial_finished_at,
            executor=None,
        )
        db = _make_db(car, task)
        payload = _build_mission_report_payload(
            msg_id or f"report-{reported_status}",
            reported_status,
            timestamp,
        )

        with patch("MQTT.receiver.AsyncSessionLocal", return_value=_FakeSessionContext(db)):
            await receiver.process_mission_report("car/10.168.1.100/task/report", payload)

        self.assertEqual(task.status, expected_status)
        self.assertEqual(task.finished_at, expected_finished_at)
        db.commit.assert_awaited_once()

    async def test_process_mission_report_maps_not_started_to_pending_for_normal_task(self):
        await self._assert_mission_report_status(
            0,
            TaskStatus.PENDING,
            is_scheduled=False,
            expected_finished_at=None,
            msg_id="report-pending",
        )

    async def test_process_mission_report_maps_not_started_to_scheduled_for_scheduled_task(self):
        await self._assert_mission_report_status(
            0,
            TaskStatus.SCHEDULED,
            is_scheduled=True,
            expected_finished_at=None,
            msg_id="report-scheduled",
        )

    async def test_process_mission_report_maps_running_status(self):
        await self._assert_mission_report_status(
            1,
            TaskStatus.RUNNING,
            expected_finished_at=None,
            msg_id="report-running",
        )

    async def test_process_mission_report_marks_task_completed_with_reported_time(self):
        reported_at = datetime.fromtimestamp(1710000100)
        await self._assert_mission_report_status(
            2,
            TaskStatus.COMPLETED,
            initial_finished_at=None,
            expected_finished_at=reported_at,
            msg_id="report-completed",
            timestamp=1710000100,
        )

    async def test_process_mission_report_maps_paused_status_without_finished_time(self):
        await self._assert_mission_report_status(
            3,
            TaskStatus.PAUSED,
            expected_finished_at=None,
            msg_id="report-paused",
        )

    async def test_process_mission_report_maps_cancelled_status_with_reported_time(self):
        reported_at = datetime.fromtimestamp(1710000200)
        await self._assert_mission_report_status(
            4,
            TaskStatus.CANCELLED,
            initial_finished_at=None,
            expected_finished_at=reported_at,
            msg_id="report-cancelled",
            timestamp=1710000200,
        )

    async def test_process_mission_report_maps_failed_status_with_reported_time(self):
        reported_at = datetime.fromtimestamp(1710000300)
        await self._assert_mission_report_status(
            5,
            TaskStatus.FAILED,
            initial_finished_at=None,
            expected_finished_at=reported_at,
            msg_id="report-failed",
            timestamp=1710000300,
        )

    async def test_process_mission_report_ignores_invalid_task_status_and_allows_retry(self):
        car = SimpleNamespace(id=7, ip_address="10.168.1.100", current_task=None)
        task = SimpleNamespace(
            id=12,
            status=TaskStatus.RUNNING,
            is_scheduled=False,
            finished_at=datetime(2024, 1, 1, 0, 0, 0),
            executor=None,
        )
        db = _make_db(car, task)
        payload = _build_mission_report_payload("report-invalid", 99)

        with patch("MQTT.receiver.AsyncSessionLocal", return_value=_FakeSessionContext(db)):
            await receiver.process_mission_report("car/10.168.1.100/task/report", payload)

        self.assertEqual(task.status, TaskStatus.RUNNING)
        self.assertEqual(task.finished_at, datetime(2024, 1, 1, 0, 0, 0))
        db.commit.assert_not_awaited()
        self.assertNotIn("report-invalid", receiver._recent_msg_ids)

    async def test_dispatch_mqtt_message_routes_by_topic(self):
        with patch("MQTT.receiver.process_car_data", new=AsyncMock()) as process_car_data, patch(
            "MQTT.receiver.process_mission_report",
            new=AsyncMock(),
        ) as process_mission_report, patch(
            "MQTT.receiver.process_live_path",
            new=AsyncMock(),
        ) as process_live_path:
            await receiver.dispatch_mqtt_message("car/10.168.1.100/status", {})
            await receiver.dispatch_mqtt_message("car/10.168.1.100/task/report", {})
            await receiver.dispatch_mqtt_message("car/10.168.1.100/task/live_path", {})

        process_car_data.assert_awaited_once_with("car/10.168.1.100/status", {})
        process_mission_report.assert_awaited_once_with("car/10.168.1.100/task/report", {})
        process_live_path.assert_awaited_once_with("car/10.168.1.100/task/live_path", {})

    async def test_process_live_path_normalizes_and_updates_state(self):
        payload = {
            "msg_id": "live-path-1",
            "version": "1.0",
            "timestamp": 1710000000,
            "data": {
                "task_id": 3,
                "segment_index": 0,
                "is_last": False,
                "points": [[1, 2], {"x": "3.5", "y": "4.5"}],
            },
        }

        with patch(
            "MQTT.receiver.update_live_path_segment",
            new=AsyncMock(return_value=({"full_points": [[1.0, 2.0], [3.5, 4.5]]}, True)),
        ) as update_live_path_segment:
            await receiver.process_live_path("car/10.168.1.100/task/live_path", payload)

        update_live_path_segment.assert_awaited_once_with(
            task_id=3,
            car_ip="10.168.1.100",
            segment_index=0,
            is_last=False,
            points=[[1.0, 2.0], [3.5, 4.5]],
        )

    async def test_process_live_path_ignores_invalid_payload_and_allows_retry(self):
        payload = {
            "msg_id": "live-path-invalid",
            "data": {
                "task_id": 3,
                "segment_index": 0,
            },
        }

        with patch("MQTT.receiver.update_live_path_segment", new=AsyncMock()) as update_live_path_segment:
            await receiver.process_live_path("car/10.168.1.100/task/live_path", payload)

        update_live_path_segment.assert_not_awaited()
        self.assertNotIn("live-path-invalid", receiver._recent_msg_ids)


if __name__ == "__main__":
    unittest.main()
