from datetime import datetime

from pydantic import BaseModel


class MapOut(BaseModel):
    id: int
    name: str
    pgm_url: str
    yaml_url: str
    preview_url: str
    resolution: float
    origin_x: float
    origin_y: float
    origin_yaw: float
    width: int
    height: int
    preview_width: int
    preview_height: int
    preview_offset_x: int
    preview_offset_y: int
    created_at: datetime
