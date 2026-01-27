from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from model import Map
from schemas import MapCreate, MapOut
from typing import List

router = APIRouter(prefix="/maps", tags=["Maps"])

# ==========================================
# 1. 创建地图 (Create)
# ==========================================
@router.post("/", response_model=MapOut, status_code=status.HTTP_201_CREATED, summary="创建一个新区域")
async def create_map(map_in: MapCreate, db: AsyncSession = Depends(get_db)):
    """
    异步创建地图：不再需要 UploadFile，直接处理 JSON 数据。
    """
    new_map = Map(
        name=map_in.name,
        center_lat=map_in.center_lat,
        center_lng=map_in.center_lng,
        zoom=map_in.zoom
    )
    
    db.add(new_map)
    await db.commit()    # 👈 必须 await
    await db.refresh(new_map) # 👈 必须 await
    
    return new_map

# ==========================================
# 2. 查询地图列表 (Read List)
# ==========================================
@router.get("/", response_model=List[MapOut], summary="查询所有地图")
async def get_maps(db: AsyncSession = Depends(get_db)):
    # SQLAlchemy 2.0 异步写法：使用 select 对象
    stmt = select(Map).order_by(Map.created_at.desc())
    result = await db.execute(stmt) # 👈 必须 await
    
    # scalars().all() 将结果集转换为模型对象列表
    return result.scalars().all()

# ==========================================
# 3. 删除地图 (Delete)
# ==========================================
@router.delete("/{map_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除一个区域")
async def delete_map(map_id: int, db: AsyncSession = Depends(get_db)):
    # 异步获取单个对象
    map_obj = await db.get(Map, map_id) # 👈 必须 await
    
    if map_obj:
        await db.delete(map_obj) # 👈 建议 await
        await db.commit()        # 👈 必须 await
        
    return None