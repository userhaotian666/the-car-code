from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from schemas import PathCreate, PathRead, PathUpdate
from model import Path
from database import get_db 

router = APIRouter(prefix="/paths", tags=["Paths"])

# ==========================================
# 1. 创建路径 (Create)
# ==========================================
@router.post("/", response_model=PathRead, status_code=status.HTTP_201_CREATED, summary="创建新路径")
async def create_path(path_in: PathCreate, db: AsyncSession = Depends(get_db)):
    """
    接收 JSON 格式的路径点数据并存入数据库。
    waypoints 字段在模型中应为 JSON 类型。
    """
    db_path = Path(**path_in.model_dump())
    db.add(db_path)
    
    await db.commit()    # 👈 异步提交
    await db.refresh(db_path) # 👈 异步刷新以获取 ID
    return db_path

# ==========================================
# 2. 查询路径列表 (Read List)
# ==========================================
@router.get("/", response_model=List[PathRead], summary="获取路径列表")
async def read_paths(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    """
    分页查询所有路径。
    """
    stmt = select(Path).offset(skip).limit(limit)
    result = await db.execute(stmt) # 👈 异步执行查询
    
    return result.scalars().all()

# ==========================================
# 3. 查询单个路径 (Read One)
# ==========================================
@router.get("/{path_id}", response_model=PathRead, summary="获取路径详情")
async def read_path(path_id: int, db: AsyncSession = Depends(get_db)):
    db_path = await db.get(Path, path_id) # 👈 异步获取
    
    if not db_path:
        raise HTTPException(status_code=404, detail="未找到该路径记录")
    return db_path

# ==========================================
# 4. 更新路径 (Update)
# ==========================================
@router.patch("/{path_id}", response_model=PathRead, summary="修改路径信息")
async def update_path(path_id: int, path_update: PathUpdate, db: AsyncSession = Depends(get_db)):
    """
    支持局部更新，例如只修改名字或只修改坐标点。
    """
    db_path = await db.get(Path, path_id)
    if not db_path:
        raise HTTPException(status_code=404, detail="未找到该路径记录")
    
    # exclude_unset=True 确保前端没传的字段不会被置为空
    update_data = path_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_path, key, value)

    await db.commit()
    await db.refresh(db_path)
    return db_path

# ==========================================
# 5. 删除路径 (Delete)
# ==========================================
@router.delete("/{path_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除指定路径")
async def delete_path(path_id: int, db: AsyncSession = Depends(get_db)):
    """
    物理删除路径。注意：如果有任务正在引用此路径，数据库可能会报外键约束错误。
    """
    db_path = await db.get(Path, path_id)
    if not db_path:
        raise HTTPException(status_code=404, detail="未找到该路径记录")
    
    await db.delete(db_path) # 👈 异步删除
    await db.commit()        # 👈 异步提交
    return None