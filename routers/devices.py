from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db  # 导入公共的 get_db
from model import DeviceDB    # 导入模型
from pydantic import BaseModel, Field

# --- Pydantic 模型 (前端数据校验) ---
class DeviceModel(BaseModel):
    name: str
    # 这里用 bool，前端传 true/false，数据库自动存 1/0
    device_status: bool = False 
    sensor_status: bool = False
    
    battery: int = Field(default=100, ge=0, le=100)
    
    ip_address: str = "192.168.1.1"

class CommandModel(BaseModel):
    action: str

router = APIRouter(prefix="/devices", tags=["Devices"])

# --- 接口 1 : 获取所有设备 ---
@router.get("/")
def get_all_devices(db: Session = Depends(get_db)):
    devices = db.query(DeviceDB).all()
    return devices

# --- 接口 2 : 获取指定ID设备 ---
@router.get("/{device_id}")
def get_device(device_id: int, db: Session = Depends(get_db)):
    device = db.query(DeviceDB).filter(DeviceDB.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

# --- 接口 3 : 创建设备 ---
@router.post("/")
def create_device(device: DeviceModel, db: Session = Depends(get_db)):
    new_device = DeviceDB(
        name=device.name,
        # Pydantic 的 True/False 会在这里自动转换
        device_status=device.device_status, 
        sensor_status=device.sensor_status,
        battery=device.battery,
        ip_address=device.ip_address
    )
    db.add(new_device)
    db.commit()
    db.refresh(new_device)
    return new_device

# --- 接口 4 : 修改设备名 ---
class DeviceRename(BaseModel):
    new_name: str

@router.post("/{device_id}/rename")
def rename_device(device_id: int, request_name: DeviceRename, db: Session = Depends(get_db)):
    device = db.query(DeviceDB).filter(DeviceDB.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    device.name = request_name.new_name
    db.commit()
    db.refresh(device)
    return {"message": f"Device {device_id} renamed successfully"}

# --- 接口 5 : 修改电量 ---
class BatteryUpdate(BaseModel):
    new_battery: int

@router.post("/{device_id}/battery")
def update_battery(device_id: int, battery_update: BatteryUpdate, db: Session = Depends(get_db)):
    device = db.query(DeviceDB).filter(DeviceDB.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if battery_update.new_battery < 0 or battery_update.new_battery > 100:
        raise HTTPException(status_code=400, detail="Battery must be between 0 and 100")
    
    device.battery = battery_update.new_battery
    db.commit()
    db.refresh(device)
    return {"message": f"Device {device_id} battery updated into {device.battery} %"}

# --- 接口 6 : 删除指定设备 ---
@router.delete("/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    #先去数据库里查，看看这个设备存不存在
    device = db.query(DeviceDB).filter(DeviceDB.id == device_id).first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # 找到了，告诉数据库要删除这个对象
    db.delete(device)  
    db.commit()
    return {"message": f"Device {device_id} deleted successfully"}
