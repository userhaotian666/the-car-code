from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from model import Car, Command
from MQTT import publish_task_command_to_car
from schemas import ReturnToBaseRequest

router = APIRouter(prefix="/commands", tags=["commands"])

RECALL_TASK_ACTION = 0
RECALL_ENABLED = 1


@router.post("/return_base")
async def return_to_base(
    req: ReturnToBaseRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Car).where(Car.id == req.car_id))
    car = result.scalars().first()
    if not car:
        raise HTTPException(status_code=404, detail=f"找不到 ID 为 {req.car_id} 的车辆")

    car_ip = (car.ip_address or "").strip()
    if not car_ip:
        raise HTTPException(status_code=400, detail="车辆未配置 IP，无法下发一键召回指令")

    new_command = Command(
        car_id=req.car_id,
        command_type="RETURN_TO_BASE",
        status=0,
        created_at=datetime.now(),
    )
    db.add(new_command)
    await db.commit()
    await db.refresh(new_command)

    try:
        await publish_task_command_to_car(
            car_ip=car_ip,
            task_id=new_command.id,
            task_action=RECALL_TASK_ACTION,
            recall=RECALL_ENABLED,
            all_pause="",
        )
    except Exception as exc:
        new_command.status = 3
        new_command.finished_at = datetime.now()
        await db.commit()
        raise HTTPException(
            status_code=502,
            detail={
                "message": "一键召回指令下发失败",
                "command_id": new_command.id,
                "mqtt_sent": False,
                "mqtt_error": str(exc),
            },
        ) from exc

    new_command.status = 1
    await db.commit()

    return {
        "code": 200,
        "message": "一键召回指令已下发",
        "data": {"command_id": new_command.id},
    }
