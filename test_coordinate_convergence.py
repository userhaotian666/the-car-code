import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from map_storage import generate_preview_and_dimensions
from routers.mission import dispatch_mission
from schemas.mission import MissionCreateRequest, Waypoint


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


class CoordinateConvergenceTests(unittest.TestCase):
    def test_preview_generation_keeps_original_dimensions_and_zero_offset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            pgm_path = tmp_path / "map.pgm"
            preview_path = tmp_path / "preview.png"
            width = 5
            height = 4

            pgm_path.write_bytes(
                b"P5\n"
                + f"{width} {height}\n255\n".encode("ascii")
                + bytes([255] * width * height)
            )

            preview_meta = generate_preview_and_dimensions(
                pgm_path,
                preview_path,
                {
                    "resolution": 0.1,
                    "origin_x": -0.2,
                    "origin_y": -0.1,
                    "origin_yaw": 0.0,
                    "negate": 0,
                    "occupied_thresh": 0.65,
                    "free_thresh": 0.196,
                },
            )

            self.assertEqual(preview_meta["width"], width)
            self.assertEqual(preview_meta["height"], height)
            self.assertEqual(preview_meta["preview_width"], width)
            self.assertEqual(preview_meta["preview_height"], height)
            self.assertEqual(preview_meta["preview_offset_x"], 0)
            self.assertEqual(preview_meta["preview_offset_y"], 0)
            self.assertTrue(preview_path.exists())


class MissionDispatchCoordinateTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_mission_stores_waypoints_as_x_y_from_lng_lat(self):
        request = MissionCreateRequest(
            car_id=7,
            name="巡逻",
            waypoints=[
                Waypoint(lng=12.5, lat=34.75),
                Waypoint(lng=-1.25, lat=0.5),
            ],
        )
        car = SimpleNamespace(id=7, name="car-7", current_task=None, current_task_id=None)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_FakeExecuteResult(car))
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.add = Mock()

        with patch("routers.mission.get_assignment_block_reason", return_value=None):
            await dispatch_mission(request, db=db)

        created_path = db.add.call_args_list[0].args[0]
        self.assertEqual(created_path.waypoints, [[12.5, 34.75], [-1.25, 0.5]])


if __name__ == "__main__":
    unittest.main()
