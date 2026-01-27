from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from typing import List

from schemas import DeviceCreate, DeviceRead, DeviceUpdate
from database import get_db 
from model import Device, Car 

router = APIRouter(prefix="/devices", tags=["Devices"])

@router.post("/", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def create_device(device: DeviceCreate, db: AsyncSession = Depends(get_db)):
    db_device = Device(**device.model_dump())
    db.add(db_device)
    await db.commit()
    await db.refresh(db_device)
    return db_device

@router.get("/", response_model=List[DeviceRead])
async def read_devices(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    stmt = select(Device).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/{device_id}", response_model=DeviceRead)
async def read_device(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@router.patch("/{device_id}", response_model=DeviceRead)
async def update_device(device_id: int, device_update: DeviceUpdate, db: AsyncSession = Depends(get_db)):
    db_device = await db.get(Device, device_id)
    if db_device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    
    update_data = device_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_device, key, value)
    
    await db.commit()
    await db.refresh(db_device)
    return db_device

@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: int, db: AsyncSession = Depends(get_db)):
    db_device = await db.get(Device, device_id)
    if db_device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    await db.delete(db_device)
    await db.commit()
    return None

@router.post("/{car_id}/bind_device/{device_id}")
async def bind_device_to_car(car_id: int, device_id: int, db: AsyncSession = Depends(get_db)):
    # 异步查询车并加载其设备列表
    stmt = select(Car).options(selectinload(Car.devices)).where(Car.id == car_id)
    car = (await db.execute(stmt)).scalars().first()
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
        
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if device in car.devices:
        return {"message": "Already bound", "success": False}
    
    car.devices.append(device)
    await db.commit()
    return {"message": "Success", "success": True}

@router.post("/{car_id}/unbind_device/{device_id}")
async def unbind_device_from_car(car_id: int, device_id: int, db: AsyncSession = Depends(get_db)):
    # 异步查询车并加载其设备列表
    stmt = select(Car).options(selectinload(Car.devices)).where(Car.id == car_id)
    car = (await db.execute(stmt)).scalars().first()
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
        
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if device not in car.devices:
        return {"message": "Device not bound to car", "success": False}
    
    car.devices.remove(device)
    await db.commit()
    return {"message": "Success", "success": True}
