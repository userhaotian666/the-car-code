from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from model import Map
from schemas import MapOut
from typing import List
from map_storage import (
    create_map_directory,
    generate_preview_and_dimensions,
    parse_map_yaml,
    remove_map_directory,
    remove_map_files_by_relative_path,
    save_upload_file,
    to_relative_upload_path,
    validate_upload_filename,
)

router = APIRouter(prefix="/maps", tags=["Maps"])


def build_map_response(map_obj: Map, request: Request) -> MapOut:
    # 数据库里存的是相对路径，例如 maps/abc123/preview.png
    # 前端真正需要的是可直接访问的完整 URL，所以这里统一做一次转换
    return MapOut(
        id=map_obj.id,
        name=map_obj.name,
        pgm_url=str(request.url_for("static", path=map_obj.pgm_path)),
        yaml_url=str(request.url_for("static", path=map_obj.yaml_path)),
        preview_url=str(request.url_for("static", path=map_obj.preview_path)),
        resolution=map_obj.resolution,
        origin_x=map_obj.origin_x,
        origin_y=map_obj.origin_y,
        origin_yaw=map_obj.origin_yaw,
        width=map_obj.width,
        height=map_obj.height,
        preview_width=map_obj.preview_width,
        preview_height=map_obj.preview_height,
        preview_offset_x=map_obj.preview_offset_x,
        preview_offset_y=map_obj.preview_offset_y,
        created_at=map_obj.created_at,
    )


@router.post("/upload", response_model=MapOut, status_code=status.HTTP_201_CREATED, summary="上传 PGM+YAML 地图")
async def upload_map(
    request: Request,
    name: str = Form(...),
    pgm_file: UploadFile = File(...),
    yaml_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    # 第一步：先校验前端传上来的文件后缀是否正确
    validate_upload_filename(pgm_file, (".pgm",), "PGM")
    yaml_suffix = validate_upload_filename(yaml_file, (".yaml", ".yml"), "YAML")

    folder_name = ""
    try:
        # 第二步：为这张地图创建独立目录
        folder_name, folder_path = create_map_directory()
        pgm_path = folder_path / "map.pgm"
        yaml_path = folder_path / f"map{yaml_suffix}"
        preview_path = folder_path / "preview.png"

        # 第三步：把前端传来的原始文件落到磁盘
        await save_upload_file(pgm_file, pgm_path)
        await save_upload_file(yaml_file, yaml_path)

        # 第四步：解析 YAML，拿到地图元数据
        yaml_meta = parse_map_yaml(yaml_path)
        # 第五步：解析 PGM，并结合 YAML 阈值生成更直观的可视化预览图
        preview_meta = generate_preview_and_dimensions(pgm_path, preview_path, yaml_meta)

        # 第六步：把“文件路径 + 元数据”写入数据库
        new_map = Map(
            name=name,
            pgm_path=to_relative_upload_path(pgm_path),
            yaml_path=to_relative_upload_path(yaml_path),
            preview_path=to_relative_upload_path(preview_path),
            resolution=yaml_meta["resolution"],
            origin_x=yaml_meta["origin_x"],
            origin_y=yaml_meta["origin_y"],
            origin_yaw=yaml_meta["origin_yaw"],
            width=preview_meta["width"],
            height=preview_meta["height"],
            preview_width=preview_meta["preview_width"],
            preview_height=preview_meta["preview_height"],
            preview_offset_x=preview_meta["preview_offset_x"],
            preview_offset_y=preview_meta["preview_offset_y"],
        )

        db.add(new_map)
        await db.commit()
        await db.refresh(new_map)
        # 返回给前端时，把相对路径转换为静态文件 URL
        return build_map_response(new_map, request)
    except HTTPException:
        # 已知的业务错误（比如文件格式不对）也要回滚数据库并清理磁盘
        await db.rollback()
        remove_map_directory(folder_name)
        raise
    except Exception as exc:
        # 未知异常统一按 500 处理，同时也清理刚刚落盘的文件
        await db.rollback()
        remove_map_directory(folder_name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"地图上传失败: {exc}"
        ) from exc

# ==========================================
# 2. 查询地图列表 (Read List)
# ==========================================
@router.get("/", response_model=List[MapOut], summary="查询所有地图")
async def get_maps(request: Request, db: AsyncSession = Depends(get_db)):
    # 返回地图列表时，按创建时间倒序展示，最新上传的排在最前面
    stmt = select(Map).order_by(Map.created_at.desc())
    result = await db.execute(stmt)
    maps = result.scalars().all()
    return [build_map_response(map_obj, request) for map_obj in maps]


@router.get("/{map_id}", response_model=MapOut, summary="获取单个地图详情")
async def get_map_detail(map_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    # 获取单张地图详情，前端通常会在查看某张地图时调用这个接口
    map_obj = await db.get(Map, map_id)
    if map_obj is None:
        raise HTTPException(status_code=404, detail="Map not found")
    return build_map_response(map_obj, request)

# ==========================================
# 3. 删除地图 (Delete)
# ==========================================
@router.delete("/{map_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除一个区域")
async def delete_map(map_id: int, db: AsyncSession = Depends(get_db)):
    # 删除时不仅要删数据库记录，还要把磁盘上的地图文件一起删掉
    map_obj = await db.get(Map, map_id)
    if map_obj is None:
        raise HTTPException(status_code=404, detail="Map not found")

    relative_pgm_path = map_obj.pgm_path
    await db.delete(map_obj)
    await db.commit()
    remove_map_files_by_relative_path(relative_pgm_path)

    return None
