from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession  # 1. 改变 Session 类型
from sqlalchemy.orm import selectinload
from typing import List, Optional
from sqlalchemy import select

from car_status import CarStatus
from car_runtime import get_effective_car_status
# 导入你的 schema 和 model
from schemas import CarCreate, CarRead, CarUpdate
from database import get_db
from model import Car, Device
router = APIRouter(prefix="/cars", tags=["Cars"])


async def _get_car_by_ip(db: AsyncSession, ip_address: str) -> Optional[Car]:
    stmt = select(Car).where(Car.ip_address == ip_address)
    result = await db.execute(stmt)
    return result.scalars().first()


async def _build_car_read(db: AsyncSession, car: Car) -> CarRead:
    car_read = CarRead.model_validate(car)
    car_read.status = await get_effective_car_status(db, car.id, car.status)
    return car_read

# ==========================================
# 1. 创建小车 (Create) - 异步版
# ==========================================
@router.post("/", response_model=CarRead, status_code=status.HTTP_201_CREATED)
async def create_car(car: CarCreate, db: AsyncSession = Depends(get_db)): # async def
    car_ip = car.ip_address.strip()
    if not car_ip:
        raise HTTPException(status_code=400, detail="Car IP is required")
    existing_car = await _get_car_by_ip(db, car_ip)
    if existing_car:
        raise HTTPException(status_code=400, detail="Car IP already exists")

    db_car = Car(**car.model_dump())
    db_car.ip_address = car_ip
    db_car.status = CarStatus.STANDBY.value
    db_car.work_status = None
    
    db.add(db_car)
    await db.commit()   # 2. 加上 await
    await db.refresh(db_car) # 3. 加上 await
    return db_car

# ==========================================
# 2. 查询小车列表 (Read List)
# ==========================================
@router.get("/", response_model=List[CarRead])
async def read_cars(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Car)
        .options(selectinload(Car.devices)) 
        .offset(skip)
        .limit(limit)
    )
    # 4. 执行查询需要 await
    result = await db.execute(stmt)
    return result.scalars().all()

# ==========================================
# 3. 查询单个小车 (Read One)
# ==========================================
@router.get("/{car_id}", response_model=CarRead)
async def read_car(car_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Car)
        .options(selectinload(Car.devices))
        .where(Car.id == car_id)
    )
    result = await db.execute(stmt)
    car = result.scalars().first()
    
    if car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    return await _build_car_read(db, car)

@router.get("/{car_id}/status", response_model=CarRead)
async def read_car_status(car_id: int, db: AsyncSession = Depends(get_db)):
    # 1. 异步查询基础车辆信息
    # 使用 selectinload 预加载关联的 devices，防止异步环境下的懒加载报错
    stmt = (
        select(Car)
        .options(selectinload(Car.devices))
        .where(Car.id == car_id)
    )
    result = await db.execute(stmt)
    car = result.scalars().first()
    
    if car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    return await _build_car_read(db, car)
# ==========================================
# 4. 更新小车 (Update)
# ==========================================
@router.patch("/{car_id}", response_model=CarRead)
async def update_car(car_id: int, car_update: CarUpdate, db: AsyncSession = Depends(get_db)):
    stmt = select(Car).options(selectinload(Car.devices)).where(Car.id == car_id)
    result = await db.execute(stmt)
    db_car = result.scalars().first()
    
    if db_car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    
    update_data = car_update.model_dump(exclude_unset=True)
    if "status" in update_data:
        raise HTTPException(status_code=400, detail="车辆状态只能由车端真实上报更新")
    if "work_status" in update_data:
        raise HTTPException(status_code=400, detail="车辆工作状态只能由车端真实上报更新")

    if "ip_address" in update_data and update_data["ip_address"] is not None:
        new_ip = update_data["ip_address"].strip()
        if not new_ip:
            raise HTTPException(status_code=400, detail="Car IP is required")
        existing_car = await _get_car_by_ip(db, new_ip)
        if existing_car and existing_car.id != car_id:
            raise HTTPException(status_code=400, detail="Car IP already exists")
        update_data["ip_address"] = new_ip

    for key, value in update_data.items():
        setattr(db_car, key, value)
    
    await db.commit() # await
    await db.refresh(db_car) # await
    return await _build_car_read(db, db_car)

# ==========================================
# 5. 删除小车 (Delete)
# ==========================================
@router.delete("/{car_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_car(car_id: int, db: AsyncSession = Depends(get_db)):
    # 5. 异步下 db.get 也要 await
    db_car = await db.get(Car, car_id)
    if db_car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    
    await db.delete(db_car) # 建议也加上 await，虽然 delete 有时在 commit 时执行，但 db.delete 本身在 AsyncSession 中是异步的
    await db.commit()
    return None

# ==========================================
# 6. 小车绑定设备
# ==========================================
@router.post("/{car_id}/bind_device/{device_id}")
async def bind_device_to_car(car_id: int, device_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Car).options(selectinload(Car.devices)).where(Car.id == car_id)
    result = await db.execute(stmt)
    car = result.scalars().first()
    
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")

    device = await db.get(Device, device_id) # await
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if device in car.devices:
         return {"message": "Device already bound", "success": False}
    
    car.devices.append(device)
    await db.commit() # await
    
    return {"message": "Success", "success": True}

@router.delete("/{car_id}/unbind_device/{device_id}")
async def unbind_device_from_car(car_id: int, device_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Car).options(selectinload(Car.devices)).where(Car.id == car_id)
    result = await db.execute(stmt)
    car = result.scalars().first()
    
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")

    device = await db.get(Device, device_id) # await
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if device not in car.devices:
         return {"message": "Device not bound", "success": False}
    
    car.devices.remove(device)
    await db.commit() # await
    
    return {"message": "Success", "success": True}
