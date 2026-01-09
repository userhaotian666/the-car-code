# schemas/__init__.py

# 从各个文件把类暴露出来
from .devices import DeviceCreate, DeviceUpdate, DeviceRead,DeviceBase
from .car import CarCreate, CarUpdate, CarRead,CarBase
from .common import CarSummary, DeviceSummary