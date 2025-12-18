from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base  # 假设你的 Base 已经是 DeclarativeBase

class PathDB(Base):
    """
    路径表 (由于你原代码没写完，我补全了基础字段以确保外键能工作)
    """
    __tablename__ = "paths"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), comment="路径名称")
    # 存储路径点坐标序列，建议用 JSON 类型，这里先用 String 占位
    coordinates: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # 反向关联：一条路径可以被多个任务使用
    tasks: Mapped[List["TaskDB"]] = relationship(back_populates="path")


class TaskDB(Base):
    """
    任务表
    """
    __tablename__ = "tasks"

    task_id: Mapped[int] = mapped_column(primary_key=True, index=True)
    task_name: Mapped[str] = mapped_column(String(50))
    
    # 0: pending, 1: in progress, 2: completed
    # 默认值 default=0 是 Python 侧的默认值
    task_status: Mapped[int] = mapped_column(default=0) 
    
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, 
        server_default=func.now()
    )
    
    # 外键关联
    path_id: Mapped[int] = mapped_column(ForeignKey("paths.id"))

    # 关系映射
    path: Mapped["PathDB"] = relationship(back_populates="tasks")
    devices: Mapped[List["DeviceDB"]] = relationship(back_populates="task")


class DeviceDB(Base):
    """
    设备(小车)表
    """
    __tablename__ = "iot_devices"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    
    # Python 类型 bool 对应数据库 Boolean (MySQL tinyint)
    device_status: Mapped[bool] = mapped_column(Boolean, default=False)
    
    ip_address: Mapped[str] = mapped_column(String(45), default="")
    
    # Optional[int] 表示这个字段可以是 int 或者 None (nullable=True)
    battery: Mapped[Optional[int]] = mapped_column(default=0)
    
    sensor_status: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, 
        server_default=func.now()
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, 
        server_default=func.now(), 
        onupdate=func.now()
    )

    # 外键：设备当前正在执行的任务 ID (可以为空，表示空闲)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.task_id"))

    # 关系映射：让你可以直接通过 device.task 访问任务对象
    task: Mapped[Optional["TaskDB"]] = relationship(back_populates="devices")