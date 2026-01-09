from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from typing import List, Optional
from sqlalchemy import select

# 导入你的 schema 和 model
from schemas import CarBase, CarCreate, CarRead, CarUpdate
from database import get_db
from model import Car, Device  # 假设你的模型都在 models.py

router = APIRouter(prefix="/cars", tags=["Cars"])

# ==========================================
# 1. 创建小车 (Create)
# ==========================================
@router.post("/", response_model=CarRead, status_code=status.HTTP_201_CREATED)
def create_car(car: CarCreate, db: Session = Depends(get_db)):
    # 1. 转换模型
    db_car = Car(**car.model_dump())
    
    # 2. 存入数据库
    db.add(db_car)
    db.commit()
    db.refresh(db_car)
    
    # 注意：新创建的车 devices 列表为空，Pydantic 会自动处理为空列表
    return db_car

# ==========================================
# 2. 查询小车列表 (Read List) - 带设备信息
# ==========================================
@router.get("/", response_model=List[CarRead])
def read_cars(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    # 【重点】：使用 options(selectinload(Car.devices))
    # 这告诉数据库：查 Car 的时候，把关联的 devices 也查出来放入内存
    stmt = (
        select(Car)
        .options(selectinload(Car.devices)) 
        .offset(skip)
        .limit(limit)
    )
    result = db.execute(stmt)
    return result.scalars().all()

# ==========================================
# 3. 查询单个小车 (Read One) - 带设备信息
# ==========================================
@router.get("/{car_id}", response_model=CarRead)
def read_car(car_id: int, db: Session = Depends(get_db)):
    # 不能直接用 db.get(Car, car_id)，因为我们需要预加载 devices
    stmt = (
        select(Car)
        .options(selectinload(Car.devices))
        .where(Car.id == car_id)
    )
    result = db.execute(stmt)
    car = result.scalars().first()
    
    if car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    return car

# ==========================================
# 4. 更新小车 (Update)
# ==========================================
@router.patch("/{car_id}", response_model=CarRead)
def update_car(car_id: int, car_update: CarUpdate, db: Session = Depends(get_db)):
    # 1. 先查找（带上 devices，因为返回模型 CarRead 需要显示它们）
    stmt = select(Car).options(selectinload(Car.devices)).where(Car.id == car_id)
    db_car = db.execute(stmt).scalars().first()
    
    if db_car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    
    # 2. 提取更新数据
    update_data = car_update.model_dump(exclude_unset=True)
    
    # 3. 更新字段
    for key, value in update_data.items():
        setattr(db_car, key, value)
    
    # 4. 提交
    db.commit()
    db.refresh(db_car) # 刷新数据
    return db_car

# ==========================================
# 5. 删除小车 (Delete)
# ==========================================
@router.delete("/{car_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_car(car_id: int, db: Session = Depends(get_db)):
    # 删除不需要加载 devices，直接查 ID 即可
    db_car = db.get(Car, car_id)
    if db_car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    
    db.delete(db_car)
    db.commit()
    return None

# ==========================================
# 6. 小车绑定设备 (复用你的逻辑，只是反过来了)
# ==========================================
@router.post("/{car_id}/bind_device/{device_id}")
def bind_device_to_car(car_id: int, device_id: int, db: Session = Depends(get_db)):
    # 1. 查车 (需要加载 devices 以便判断是否已存在)
    stmt = select(Car).options(selectinload(Car.devices)).where(Car.id == car_id)
    car = db.execute(stmt).scalars().first()
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")

    # 2. 查设备
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # 3. 判重
    # 注意：因为上面用了 selectinload，car.devices 是可用的
    if device in car.devices:
         return {"message": "Device already bound to this car", "success": False}
    
    # 4. 绑定
    car.devices.append(device)
    db.commit()
    
    return {"message": f"Device {device.name} bound to Car {car.name}", "success": True}

# ==========================================
# 7. 小车解绑设备
# ==========================================
@router.delete("/{car_id}/unbind_device/{device_id}")
def unbind_device_from_car(car_id: int, device_id: int, db: Session = Depends(get_db)):
    # 1. 查车 (一定要加载 devices)
    stmt = select(Car).options(selectinload(Car.devices)).where(Car.id == car_id)
    car = db.execute(stmt).scalars().first()
    
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    
    # 2. 在列表中找到对应的设备对象
    target_device = next((d for d in car.devices if d.id == device_id), None)
    
    if not target_device:
        raise HTTPException(status_code=404, detail="Device is not bound to this car")
    
    # 3. 移除
    car.devices.remove(target_device)
    db.commit()
    
    return {"message": "Device unbound successfully", "success": True}