from datetime import datetime, time
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import (
    String, Integer, SmallInteger, DateTime, ForeignKey, 
    JSON, DECIMAL, BigInteger, Float, Index, Time, Boolean, Date
)
from sqlalchemy.orm import Mapped, mapped_column, relationship,validates
from database import Base
from car_status import CarStatus

# 使用 TYPE_CHECKING 避免循环导入
if TYPE_CHECKING:
    pass

import enum

class TaskStatus(enum.IntEnum):
    PENDING = 0      # 待处理/普通任务初始
    SCHEDULED = 1    # 已定时（等待时间到达）
    RUNNING = 2      # 执行中
    COMPLETED = 3    # 已完成
    FAILED = 4       # 失败
    CANCELLED = 5    # 已取消
    PAUSED = 6       # 暂停中

# ================= 1. 地图表 (Map) =================
class Map(Base):
    __tablename__ = "maps"

    # 这张表现在不再保存“中心点经纬度地图”，
    # 而是保存一张激光雷达栅格地图对应的：
    # 1. 文件路径
    # 2. 地图元数据
    # 3. 图片尺寸信息
    id: Mapped[int] = mapped_column(primary_key=True, comment="区域ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="区域名称")

    # 三个 path 都是“相对 uploads/ 目录的路径字符串”，不是文件内容本身
    # 例如：maps/abc123/map.pgm
    pgm_path: Mapped[str] = mapped_column(String(255), nullable=False, comment="PGM地图相对路径")
    yaml_path: Mapped[str] = mapped_column(String(255), nullable=False, comment="YAML配置相对路径")
    preview_path: Mapped[str] = mapped_column(String(255), nullable=False, comment="PNG预览图相对路径")

    # resolution 表示“每个像素对应现实世界多少米”
    # origin_x / origin_y / origin_yaw 来自地图 YAML 文件里的 origin
    # 后续前端要把车辆位置画到地图上，就要依赖这些值做换算
    resolution: Mapped[float] = mapped_column(Float, nullable=False, comment="地图分辨率(米/像素)")
    origin_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="地图原点X")
    origin_y: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="地图原点Y")
    origin_yaw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="地图原点朝向")

    # width / height 是地图图片本身的像素尺寸
    # 前端显示和坐标映射时也会用到
    width: Mapped[int] = mapped_column(Integer, nullable=False, comment="地图宽度(像素)")
    height: Mapped[int] = mapped_column(Integer, nullable=False, comment="地图高度(像素)")

    # 预览图在后端会做主体裁剪，所以需要额外记录裁剪后的尺寸和偏移量
    preview_width: Mapped[int] = mapped_column(Integer, nullable=False, comment="预览图宽度(像素)")
    preview_height: Mapped[int] = mapped_column(Integer, nullable=False, comment="预览图高度(像素)")
    preview_offset_x: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="预览图相对原图的X偏移")
    preview_offset_y: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="预览图相对原图的Y偏移")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # 异步建议使用 selectin 加载
    tasks: Mapped[List["Task"]] = relationship(back_populates="map_info", lazy="selectin")
    
# ================= 2. 路径表 (Path) =================
class Path(Base):
    __tablename__ = "paths"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="任务ID/路径ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="名字")
    waypoints: Mapped[list] = mapped_column(JSON, nullable=False, comment="路径坐标点集合，格式为 [[x, y], ...]")

# ================= 3. 任务表 (Task) =================
class Task(Base):
    __tablename__ = "tasks"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="任务id")
    name: Mapped[str] = mapped_column(String(100), comment="名字")
    
    # 修改 status：使用枚举类型，默认值为 PENDING (0)
    status: Mapped[TaskStatus] = mapped_column(
        SmallInteger, 
        default=TaskStatus.PENDING, 
        comment="任务状态: 0-待处理, 1-已定时, 2-执行中, 3-已完成, 4-失败, 5-取消, 6-暂停"
    )
    
    # 定时相关字段
    is_scheduled: Mapped[bool] = mapped_column(
        Boolean, 
        default=False, 
        comment="是否为定时任务: 0-普通任务, 1-定时任务"
    )
    scheduled_start: Mapped[Optional[time]] = mapped_column(
        Time, nullable=True, comment="预计开始时间"
    )
    scheduled_end: Mapped[Optional[time]] = mapped_column(
        Time, nullable=True, comment="预计结束时间"
    )

    # ... (map_id, path_id, created_at 等其他字段保持不变) ...
    map_id: Mapped[Optional[int]] = mapped_column(ForeignKey("maps.id"))
    path_id: Mapped[Optional[int]] = mapped_column(ForeignKey("paths.id"))
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 关系定义保持不变
    map_info: Mapped["Map"] = relationship(back_populates="tasks", lazy="selectin")
    path_info: Mapped["Path"] = relationship(lazy="selectin")
    problems: Mapped[List["Problem"]] = relationship(back_populates="task", lazy="selectin")

    executor: Mapped[Optional["Car"]] = relationship(
        "Car", 
        back_populates="current_task",
        uselist=False,
        lazy="selectin"
    )

    # --- 逻辑校验 (可选) ---
    @validates("is_scheduled")
    def validate_scheduled_task(self, key, value):
        # 如果设为定时任务，但 status 还没改，可以自动将其修正为 SCHEDULED 状态
        if value is True and self.status == TaskStatus.PENDING:
            self.status = TaskStatus.SCHEDULED
        return value


# ================= 4. 小车表 (Car) =================
class Car(Base):
    __tablename__ = "cars"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="小车ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False, unique=True, comment="小车IP地址")
    
    current_task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"))
    status: Mapped[int] = mapped_column(
        SmallInteger,
        default=CarStatus.STANDBY.value,
        comment="车辆状态: 0-待机, 1-充电执行中, 2-任务执行中, 3-任务完成返回中, 4-异常状态",
    )
    work_status: Mapped[Optional[int]] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="车辆工作状态，由车端状态上报实时更新",
    )
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
    
    battery: Mapped[Optional[int]] = mapped_column(SmallInteger, comment="电池信息")
    temperature: Mapped[Optional[float]] = mapped_column(Float, comment="温度(℃)")
    speed: Mapped[Optional[float]] = mapped_column(Float, comment="速度(m/s)")
    signal: Mapped[Optional[int]] = mapped_column(SmallInteger, comment="信号强度")
    
    longitude: Mapped[Optional[float]] = mapped_column(DECIMAL(10, 7), comment="地图相对X坐标")
    latitude: Mapped[Optional[float]] = mapped_column(DECIMAL(10, 7), comment="地图相对Y坐标")
    yaw: Mapped[Optional[float]] = mapped_column(Float, comment="相对地图原点的朝向(度)")
    
    mode: Mapped[Optional[int]] = mapped_column(SmallInteger, comment="模式: 1-遥控, 2-自主导航")
    car_status: Mapped[Optional[int]] = mapped_column(SmallInteger, comment="小车状态")
    work_status: Mapped[Optional[int]] = mapped_column(SmallInteger, comment="小车工作状态")
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.now, nullable=False, comment="上报时间")

    __table_args__ = (
        Index("idx_car_time", "car_id", "reported_at"),
    )

class TaskSchedule(Base):
    __tablename__ = "task_schedules"
    
    id: Mapped[int] = mapped_column(primary_key=True, comment="调度ID")
    name: Mapped[str] = mapped_column(String(100), comment="计划名称")
    
    # 核心配置
    run_time: Mapped[time] = mapped_column(Time, nullable=False, comment="每天执行时间")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    
    # 任务参数
    map_id: Mapped[int] = mapped_column(ForeignKey("maps.id"), nullable=False)
    path_id: Mapped[Optional[int]] = mapped_column(ForeignKey("paths.id"), nullable=True)
    default_car_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cars.id"), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # 简单的关系定义 (如果不需要反向查询，可以不写 back_populates)
    # 记得导入 Map, Path, Car 类
