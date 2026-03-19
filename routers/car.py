from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession  # 1. 改变 Session 类型
from sqlalchemy.orm import selectinload
from typing import List
from sqlalchemy import select

# 导入你的 schema 和 model
from schemas import CarCreate, CarRead, CarUpdate
from database import get_db
from model import Car, Device ,CarHistory
from CRUD import get_latest_car_status_async  # 导入异步查询函数
router = APIRouter(prefix="/cars", tags=["Cars"])

# ==========================================
# 1. 创建小车 (Create) - 异步版
# ==========================================
@router.post("/", response_model=CarRead, status_code=status.HTTP_201_CREATED)
async def create_car(car: CarCreate, db: AsyncSession = Depends(get_db)): # async def
    db_car = Car(**car.model_dump())
    
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
    return car

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
    
    # 2. 调用你之前改好的异步查询函数，获取最新的历史状态
    # 这里的 db 会话是共享的，完全没问题
    latest_history = await get_latest_car_status_async(db, car_id)
    
    if latest_history:
        # 注意：这里是将历史表的数据临时“挂载”到小车对象上返回给前端
        # 确保你的 CarRead Schema 中定义了 status 和 last_update 字段
        
        # 加上 is not None 的判断，明确排除 None 的情况，完美解决 Pylance 报错
        if latest_history.car_status is not None:
            car.status = latest_history.car_status
        else:
            # 可选：如果历史记录里的状态碰巧是 None，你可以让它保持小车原本的状态，或者给个默认值比如 0
            pass 
            # car.status = 0
    
    return car
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
    for key, value in update_data.items():
        setattr(db_car, key, value)
    
    await db.commit() # await
    await db.refresh(db_car) # await
    return db_car

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

