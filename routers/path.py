from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List
from schemas import PathCreate, PathRead, PathUpdate
from model import Path
from database import get_db 

router = APIRouter(prefix="/paths", tags=["Paths"])

# 1. 创建路径 (Create Path)
# 前端在地图上点选后，发送 JSON 格式：
# {
#   "name": "巡逻路线A",
#   "waypoints": [{"x": 120.123, "y": 30.123}, {"x": 120.456, "y": 30.456}]
# }
@router.post("/", response_model=PathRead, status_code=status.HTTP_201_CREATED, summary="创建路径")
def create_path(path_in: PathCreate, db: Session = Depends(get_db)):
    # model_dump() 会将 Pydantic 模型转为字典
    # path_in.waypoints 是 [Waypoint(x=.., y=..), ...] 
    # model_dump() 后变成 [{"x":.., "y":..}, ...]，这正是 JSON 列需要的格式
    path_data = path_in.model_dump()
    
    # 实例化 SQLAlchemy 模型
    # 注意：SQLAlchemy 的 JSON 类型字段可以直接接受 Python 的 list/dict 结构
    db_path = Path(**path_data)
    
    db.add(db_path)
    db.commit()
    db.refresh(db_path) # 刷新以获取自动生成的 ID
    
    return db_path

# 2. 查询路径列表 (Read List) - 补充接口
@router.get("/", response_model=List[PathRead], summary="查询路径列表")
def read_paths(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    stmt = select(Path).offset(skip).limit(limit)
    result = db.execute(stmt)
    return result.scalars().all()

# 3. 查询单个路径 (Read One) - 补充接口
@router.get("/{path_id}", response_model=PathRead, summary="查询单个路径详情")
def read_path(path_id: int, db: Session = Depends(get_db)):
    db_path = db.get(Path, path_id)
    if db_path is None:
        raise HTTPException(status_code=404, detail="Path not found")
    return db_path

# 4. 更新路径 (Update) - 补充接口 (例如修改了地图上的点)
@router.patch("/{path_id}", response_model=PathRead, summary="更新路径(支持只改名字)")
def update_path(path_id: int, path_update: PathUpdate, db: Session = Depends(get_db)):
    # 1. 查数据
    db_path = db.get(Path, path_id)
    if not db_path:
        raise HTTPException(status_code=404, detail="Path not found")
    
    # 2. 提取需要更新的数据
    # 【关键点】exclude_unset=True
    # 它的作用是：前端没传的字段，不会变成 None，而是直接忽略。
    # 比如前端只传了 {"name": "新名字"}，这里得到的字典就是 {"name": "新名字"}，不会覆盖原有的 waypoints
    update_data = path_update.model_dump(exclude_unset=True)
    
    # 3. 遍历更新
    for key, value in update_data.items():
        setattr(db_path, key, value)

    db.commit()
    db.refresh(db_path)
    return db_path

# 5. 删除路径 (Delete)
@router.delete("/{path_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除指定路径")
def delete_path(path_id: int, db: Session = Depends(get_db)):
    # 1. 根据主键查找数据
    db_path = db.get(Path, path_id)
    
    # 2. 如果没找到，抛出 404 错误
    if db_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Path not found"
        )
    
    # 3. 删除并提交事务
    db.delete(db_path)
    db.commit()
    
    # 4. 返回 None (配合 status_code=204，表示操作成功但没有内容返回)
    return None