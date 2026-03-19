from pydantic import BaseModel

class ReturnToBaseRequest(BaseModel):
    car_id: int
    # 删除了 current_longitude 和 current_latitude
