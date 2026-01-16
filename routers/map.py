from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from model import Map
from schemas import MapCreate, MapOut # 导入刚才改好的schema

router = APIRouter(prefix="/maps", tags=["Maps"])

@router.post("/", response_model=MapOut, summary="创建一个新区域")
def create_map(map_in: MapCreate, db: Session = Depends(get_db)):
    """
    不再需要 UploadFile,直接接收 JSON 数据
    """
    new_map = Map(
        name=map_in.name,
        center_lat=map_in.center_lat,
        center_lng=map_in.center_lng,
        zoom=map_in.zoom
    )
    
    db.add(new_map)
    db.commit()
    db.refresh(new_map)
    
    return new_map

@router.get("/", response_model=list[MapOut])
def get_maps(db: Session = Depends(get_db)):
    return db.query(Map).all()

@router.delete("/{map_id}", status_code=204, summary="删除一个区域")
def delete_map(map_id: int, db: Session = Depends(get_db)):
    map_obj = db.get(Map, map_id)
    if map_obj:
        db.delete(map_obj)
        db.commit()
    return None

