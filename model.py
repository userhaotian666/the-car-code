from datetime import datetime
from typing import Optional, List,TYPE_CHECKING
from sqlalchemy import create_engine, String, Integer, SmallInteger, DateTime, ForeignKey, JSON, DECIMAL, BigInteger, text,Float, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base  # 假设你的 Base 已经是 DeclarativeBase

if TYPE_CHECKING:
    pass
# ================= 1. 地图表 (Map) [cite: 15, 16] =================
class Map(Base):
    __tablename__ = "maps"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="区域ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="区域名称")
    # 纬度 (如 39.90923)
    center_lat: Mapped[float] = mapped_column(Float, nullable=False, comment="中心点纬度") 
    # 经度 (如 116.397428)
    center_lng: Mapped[float] = mapped_column(Float, nullable=False, comment="中心点经度")
    # 缩放级别 (默认16，既能看清路也能看清楼)
    zoom: Mapped[int] = mapped_column(Integer, default=16, comment="默认缩放级别")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # 关系不用变
    tasks: Mapped[List["Task"]] = relationship(back_populates="map_info")
    
# ================= 2. 路径表 (Path) [cite: 9, 10] =================
class Path(Base):
    __tablename__ = "paths"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="任务ID/路径ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="名字")
    # 使用 JSON 存储坐标点集合 [{"x":1, "y":2}, ...]
    waypoints: Mapped[list] = mapped_column(JSON, nullable=False, comment="路径坐标点集合")

# ================= 3. 任务表 (Task) [cite: 7, 8] =================
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
    map_info: Mapped["Map"] = relationship(back_populates="tasks")
    path_info: Mapped["Path"] = relationship()
    problems: Mapped[List["Problem"]] = relationship(back_populates="task")

    # 【新增关键代码】
    # 1. Mapped["Car"]：加引号，告诉 Python 这是一个“稍后解析”的类型
    # 2. relationship("Car", ...)：加引号，告诉 SQLAlchemy 去找名为 "Car" 的表映射
    # 3. uselist=False：表示这是一对一关系（一个任务当前只能被一个车执行）
    executor: Mapped[Optional["Car"]] = relationship(
        "Car", 
        back_populates="current_task",
        uselist=False 
    )

# ================= 4. 小车表 (Car) [cite: 1, 2] =================
class Car(Base):
    __tablename__ = "cars"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="小车ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    
    current_task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"))
    status: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # 【修改关键代码】
    # 1. relationship("Task", ...)：使用字符串 "Task" 指向任务表
    # 2. back_populates="executor"：这里的字符串必须对应 Task 类里的属性名 "executor"
    current_task: Mapped["Task"] = relationship(
        "Task", 
        back_populates="executor"
    )
    
    devices: Mapped[List["Device"]] = relationship(
        "Device", # 建议这里也都改成字符串 "Device" 保持风格统一
        secondary="car_device_relations",
        back_populates="cars"
    )
# ================= 5. 设备表 (Device) [cite: 5, 6] =================
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

    # 反向关系
    cars: Mapped[List["Car"]] = relationship(
        secondary="car_device_relations",
        back_populates="devices"
    )

# ================= 6. 关联表 (Relation) [cite: 3, 4] =================
class CarDeviceRelation(Base):
    __tablename__ = "car_device_relations"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)

# ================= 7. 报错表 (Problem) [cite: 11, 12] =================
class Problem(Base):
    __tablename__ = "problems"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="报错ID")
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), comment="关联任务ID")
    name: Mapped[str] = mapped_column(String(50), comment="问题名字")
    description: Mapped[Optional[str]] = mapped_column(String(100), comment="问题描述")
    
    task: Mapped["Task"] = relationship(back_populates="problems")

# ================= 8. 命令表 (Command) [cite: 13, 14] =================
class Command(Base):
    __tablename__ = "commands"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="命令ID")
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id"), comment="对哪个车发送")
    device_id: Mapped[Optional[int]] = mapped_column(ForeignKey("devices.id"), comment="设备ID")
    command_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="指令类型")
    status: Mapped[int] = mapped_column(SmallInteger, default=0, comment="0:pending, 1:sent, 2:success, 3:failed")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

# ================= 9. 历史表/动态数据 (History) [cite: 17, 18] =================
class CarHistory(Base):
    __tablename__ = "car_history"
    
    # 数据量大，使用 BigInteger
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id", ondelete="CASCADE"))
    
    battery: Mapped[int] = mapped_column(SmallInteger, comment="电池信息")
    # 经纬度必须用 DECIMAL 保证精度
    longitude: Mapped[float] = mapped_column(DECIMAL(10, 7), comment="经度")
    latitude: Mapped[float] = mapped_column(DECIMAL(10, 7), comment="纬度")
    
    car_status: Mapped[int] = mapped_column(SmallInteger, comment="小车状态")
    # 毫秒级时间戳
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, comment="上报时间")

    __table_args__ = (
        # 创建一个名为 idx_car_time 的复合索引
        # 索引顺序：先按 car_id 分组，再按 reported_at 排序
        Index("idx_car_time", "car_id", "reported_at"),
    )


