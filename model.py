from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import (
    String, Integer, SmallInteger, DateTime, ForeignKey, 
    JSON, DECIMAL, BigInteger, Float, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

# 使用 TYPE_CHECKING 避免循环导入
if TYPE_CHECKING:
    pass

# ================= 1. 地图表 (Map) =================
class Map(Base):
    __tablename__ = "maps"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="区域ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="区域名称")
    center_lat: Mapped[float] = mapped_column(Float, nullable=False, comment="中心点纬度") 
    center_lng: Mapped[float] = mapped_column(Float, nullable=False, comment="中心点经度")
    zoom: Mapped[int] = mapped_column(Integer, default=16, comment="默认缩放级别")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # 异步建议使用 selectin 加载
    tasks: Mapped[List["Task"]] = relationship(back_populates="map_info", lazy="selectin")
    
# ================= 2. 路径表 (Path) =================
class Path(Base):
    __tablename__ = "paths"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="任务ID/路径ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="名字")
    waypoints: Mapped[list] = mapped_column(JSON, nullable=False, comment="路径坐标点集合")

# ================= 3. 任务表 (Task) =================
class Task(Base):
    __tablename__ = "tasks"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="任务id")
    name: Mapped[str] = mapped_column(String(100), comment="名字")
    status: Mapped[int] = mapped_column(SmallInteger, default=0, comment="状态")
    
    map_id: Mapped[Optional[int]] = mapped_column(ForeignKey("maps.id"))
    path_id: Mapped[Optional[int]] = mapped_column(ForeignKey("paths.id"))
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 关系定义
    map_info: Mapped["Map"] = relationship(back_populates="tasks", lazy="selectin")
    path_info: Mapped["Path"] = relationship(lazy="selectin")
    problems: Mapped[List["Problem"]] = relationship(back_populates="task", lazy="selectin")

    # 执行者：一对一关系
    executor: Mapped[Optional["Car"]] = relationship(
        "Car", 
        back_populates="current_task",
        uselist=False,
        lazy="selectin"
    )

# ================= 4. 小车表 (Car) =================
class Car(Base):
    __tablename__ = "cars"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="小车ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    
    current_task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"))
    status: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    current_task: Mapped["Task"] = relationship(
        "Task", 
        back_populates="executor",
        lazy="selectin"
    )
    
    devices: Mapped[List["Device"]] = relationship(
        "Device",
        secondary="car_device_relations",
        back_populates="cars",
        lazy="selectin"
    )

# ================= 5. 设备表 (Device) =================
class Device(Base):
    __tablename__ = "devices"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="设备ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="设备名称")
    status: Mapped[int] = mapped_column(SmallInteger, default=1, comment="设备状态")
    device_type: Mapped[Optional[str]] = mapped_column(String(50), comment="设备类型")
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), comment="IP地址")
    url: Mapped[Optional[str]] = mapped_column(String(100), comment="视频流")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    cars: Mapped[List["Car"]] = relationship(
        "Car",
        secondary="car_device_relations",
        back_populates="devices",
        lazy="selectin"
    )

# ================= 6. 关联表 (Relation) =================
class CarDeviceRelation(Base):
    __tablename__ = "car_device_relations"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)

# ================= 7. 报错表 (Problem) =================
class Problem(Base):
    __tablename__ = "problems"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="报错ID")
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), comment="关联任务ID")
    name: Mapped[str] = mapped_column(String(50), comment="问题名字")
    description: Mapped[Optional[str]] = mapped_column(String(100), comment="问题描述")
    
    task: Mapped["Task"] = relationship(back_populates="problems", lazy="selectin")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

# ================= 8. 命令表 (Command) =================
class Command(Base):
    __tablename__ = "commands"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="命令ID")
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id"), comment="对哪个车发送")
    device_id: Mapped[Optional[int]] = mapped_column(ForeignKey("devices.id"), comment="设备ID")
    command_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="指令类型")
    status: Mapped[int] = mapped_column(SmallInteger, default=0, comment="0:pending, 1:sent, 2:success, 3:failed")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

# ================= 9. 历史表 (History) =================
class CarHistory(Base):
    __tablename__ = "car_history"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id", ondelete="CASCADE"))
    
    battery: Mapped[int] = mapped_column(SmallInteger, comment="电池信息")
    temperature: Mapped[float] = mapped_column(Float, comment="温度(℃)")
    speed: Mapped[float] = mapped_column(Float, comment="速度(m/s)")
    signal: Mapped[int] = mapped_column(SmallInteger, comment="信号强度")
    
    longitude: Mapped[float] = mapped_column(DECIMAL(10, 7), comment="经度")
    latitude: Mapped[float] = mapped_column(DECIMAL(10, 7), comment="纬度")
    
    car_status: Mapped[int] = mapped_column(SmallInteger, comment="小车状态")
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.now, nullable=False, comment="上报时间")

    __table_args__ = (
        Index("idx_car_time", "car_id", "reported_at"),
    )