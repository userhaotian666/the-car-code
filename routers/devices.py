from fastapi import APIRouter, Depends, HTTPException,status
from sqlalchemy.orm import Session,joinedload
from typing import Optional, List
from sqlalchemy import select

from schemas import DeviceBase, DeviceCreate, DeviceRead, DeviceUpdate
from database import get_db  # 导入公共的 get_db
from model import Device,Car  # 导入模型

router = APIRouter(prefix="/devices", tags=["Devices"])

# 1. 创建设备 (Create)
@router.post("/", response_model=DeviceRead, status_code=status.HTTP_201_CREATED,summary="创建设备")
def create_device(device: DeviceCreate, db: Session = Depends(get_db)):
    # 将 Pydantic 模型转换为 SQLAlchemy 模型
    db_device = Device(**device.model_dump())
    db.add(db_device)
    db.commit()
    db.refresh(db_device) # 刷新以获取自动生成的 ID 和 created_at
    return db_device

# 2. 查询设备列表 (Read List)
@router.get("/", response_model=List[DeviceRead],summary="查询设备列表")
def read_devices(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    # SQLAlchemy 2.0 推荐写法: select(Model)
    stmt = select(Device).offset(skip).limit(limit)
    result = db.execute(stmt)
    # scalars().all() 将结果转换为模型对象列表
    return result.scalars().all()

# 3. 查询单个设备 (Read One)
@router.get("/{device_id}", response_model=DeviceRead,summary="查询单个设备")
def read_device(device_id: int, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

# 4. 更新设备 (Update)
@router.patch("/{device_id}", response_model=DeviceRead,summary="更新设备")
def update_device(device_id: int, device_update: DeviceUpdate, db: Session = Depends(get_db)):
    # 查找现有设备
    db_device = db.get(Device, device_id)
    if db_device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # 提取需要更新的数据 (exclude_unset=True 确保只更新用户传来的字段)
    update_data = device_update.model_dump(exclude_unset=True)
    
    # 遍历并更新属性
    for key, value in update_data.items():
        setattr(db_device, key, value)
    
    # 手动更新 updated_at (有些数据库配置可能需要手动触发)
    # db_device.updated_at = datetime.now() 
    
    db.commit()
    db.refresh(db_device)
    return db_device

# 5. 删除设备 (Delete)
@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT,summary="删除设备")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    db_device = db.get(Device, device_id)
    if db_device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    
    db.delete(db_device)
    db.commit()
    return None

#6. 设备绑定车
@router.post("/{car_id}/bind_device/{device_id}",summary="设备绑定车")
def bind_device_to_car(car_id: int, device_id: int, db: Session = Depends(get_db)):
    # 第一步：查出车
    car = db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
        
    # 第二步：查出设备
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # 第三步：检查是否已经绑定了 (防止重复绑定)
    if device in car.devices:
        return {"message": "Device already bound to this car", "success": False}
    
    # 第四步：建立关系 (SQLAlchemy 会自动处理中间表)
    # 你不需要手动去 insert car_device_relations 表，直接 append 即可
    car.devices.append(device)
    
    db.commit()
    return {"message": f"Device {device.name} bound to Car {car.name}", "success": True}

#7. 设备从车上解绑
@router.delete("/{car_id}/unbind_device/{device_id}",summary="设备从车上解绑")
def unbind_device_from_car(car_id: int, device_id: int, db: Session = Depends(get_db)):
    # 查车（注意：需要加载 devices，否则 remove 时可能会报错或需要触发懒加载）
    # 这里为了稳妥，显式加载 devices
    stmt = select(Car).options(joinedload(Car.devices)).where(Car.id == car_id)
    car = db.execute(stmt).scalars().first()
    
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    
    # 在 car.devices 列表中查找这个设备
    # 注意：这里不能简单用 id 判断，要在列表里找到对应的 ORM 对象
    target_device = next((d for d in car.devices if d.id == device_id), None)
    
    if not target_device:
        raise HTTPException(status_code=404, detail="Device is not bound to this car")
    
    # 移除关系
    car.devices.remove(target_device)
    
    db.commit()
    return {"message": "Device unbound successfully", "success": True}