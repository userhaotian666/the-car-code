# schemas/__init__.py

# 从各个文件把类暴露出来
from .devices import DeviceCreate, DeviceUpdate, DeviceRead,DeviceBase
from .car import CarCreate, CarUpdate, CarRead,CarBase
from .common import CarSummary, DeviceSummary, PathSimple, CarSimple
from .map import MapCreate,MapOut
from .mission import Waypoint,MissionCreateRequest
from .history import CarRealtimeResponse
from .path import PathCreate, PathRead, Waypoint as PathWaypoint, PathUpdate
from .task import TaskCreate, TaskRead, TaskBase