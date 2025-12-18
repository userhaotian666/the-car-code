from sqlalchemy import create_engine, Column, Integer, String, TIMESTAMP, Boolean,ForeignKey
from database import Base 
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class DeviceDB(Base):
    __tablename__ = "iot_devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    
    # 这里用 Boolean，MySQL 里会自动存为 tinyint(1)
    device_status = Column(Boolean, default=False, nullable=False)
    
    ip_address = Column(String(45), default="", nullable=False)
    
    battery = Column(Integer, default=0, nullable=True)
    
    sensor_status = Column(Boolean, default=False, nullable=False)

    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    
    updated_at = Column(
        TIMESTAMP, 
        server_default=func.now(), 
        onupdate=func.now(), 
        nullable=False
    )

    task_id=Column(Integer, ForeignKey("tasks.task_id"), nullable=True)

class TaskDB(Base):
    __tablename__ = "tasks"

    task_id = Column(Integer, primary_key=True, index=True)
    task_name=Column(String(50), nullable=False)
    task_status=Column(Integer, default=0, nullable=False)  # 0: pending, 1: in progress, 2: completed
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    path_id=Column(Integer, ForeignKey("paths.id"), nullable=False)

class PathDB(Base):
    __tablename__ = "paths"

    
