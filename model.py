from datetime import datetime
from typing import Optional, List
from sqlalchemy import create_engine, String, Integer, SmallInteger, DateTime, ForeignKey, JSON, DECIMAL, BigInteger, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base  # 假设你的 Base 已经是 DeclarativeBase

# ================= 1. 地图表 (Map) [cite: 15, 16] =================
class Map(Base):
    __tablename__ = "maps"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="名字")
    path: Mapped[Optional[str]] = mapped_column(String(255), comment="路径文件地址")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")

    # 反向关系：一个地图可以被多个任务使用
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
    status: Mapped[int] = mapped_column(SmallInteger, default=0, comment="状态:0未开始,1进行中,2已完成,3异常")
    
    # 外键关联
    map_id: Mapped[Optional[int]] = mapped_column(ForeignKey("maps.id"), comment="关联map表")
    path_id: Mapped[Optional[int]] = mapped_column(ForeignKey("paths.id"), comment="关联path表")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ORM 关系
    map_info: Mapped["Map"] = relationship(back_populates="tasks")
    path_info: Mapped["Path"] = relationship()
    problems: Mapped[List["Problem"]] = relationship(back_populates="task")

# ================= 4. 小车表 (Car) [cite: 1, 2] =================
class Car(Base):
    __tablename__ = "cars"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="小车ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="小车名字")
    
    # 关联当前正在执行的任务 (使用字符串 'Task' 避免循环导入问题)
    current_task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), comment="当前任务ID")
    
    status: Mapped[int] = mapped_column(SmallInteger, default=0, comment="小车状态:0-空闲,1-任务中...")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # ORM 高级查询关系
    current_task: Mapped["Task"] = relationship()
    
    # 多对多关系：通过中间表直接获取设备列表 (car.devices)
    devices: Mapped[List["Device"]] = relationship(
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
