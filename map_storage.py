from __future__ import annotations

import shutil
from pathlib import Path
from typing import cast
from uuid import uuid4

import numpy as np
import yaml
from PIL import Image, ImageDraw, UnidentifiedImageError
from scipy import ndimage
from fastapi import HTTPException, UploadFile, status

# uploads 是所有上传文件的根目录
# maps 是地图文件专用目录，所有地图都会放到这里面
UPLOAD_ROOT = Path(__file__).resolve().parent / "uploads"
MAPS_ROOT = UPLOAD_ROOT / "maps"


def ensure_storage_root() -> None:
    # 确保 uploads/maps 目录存在
    # 第一次启动项目时，如果目录不存在，这里会自动创建
    MAPS_ROOT.mkdir(parents=True, exist_ok=True)


def create_map_directory() -> tuple[str, Path]:
    # 每上传一张地图，都创建一个独立的随机文件夹
    # 这样 PGM / YAML / preview.png 会被放在同一个目录里，便于后续删除和管理
    ensure_storage_root()
    folder_name = uuid4().hex
    folder_path = MAPS_ROOT / folder_name
    folder_path.mkdir(parents=True, exist_ok=False)
    return folder_name, folder_path


async def save_upload_file(upload: UploadFile, destination: Path) -> None:
    # 把前端上传的文件内容读取出来，然后原样写入目标路径
    # 这里不做任何解析，只负责“把文件保存到磁盘”
    content = await upload.read()
    destination.write_bytes(content)


def validate_upload_filename(upload: UploadFile, allowed_suffixes: tuple[str, ...], label: str) -> str:
    # 只根据文件后缀做一次基础校验
    # 例如：PGM 只能是 .pgm，YAML 只能是 .yaml / .yml
    filename = upload.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} 文件格式错误，支持: {', '.join(allowed_suffixes)}"
        )
    return suffix


def parse_map_yaml(yaml_path: Path) -> dict[str, float]:
    # 解析地图对应的 YAML 文件
    # 我们重点只提取地图显示和坐标换算需要的几个字段：
    # - resolution: 每像素代表多少米
    # - origin: 地图原点在世界坐标中的位置和朝向
    try:
        raw_data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        # 有些 YAML 文件会带 BOM 头，utf-8 失败时再尝试 utf-8-sig
        raw_data = yaml.safe_load(yaml_path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"YAML 解析失败: {exc}"
        ) from exc

    if not isinstance(raw_data, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="YAML 内容必须是对象结构"
        )

    required_fields = ("image", "resolution", "origin")
    missing_fields = [field for field in required_fields if field not in raw_data]
    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"YAML 缺少必要字段: {', '.join(missing_fields)}"
        )

    origin = raw_data["origin"]
    if not isinstance(origin, (list, tuple)) or len(origin) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="YAML 中的 origin 必须是至少包含 3 个数值的数组"
        )

    try:
        # 统一把 YAML 里的值转成 float，方便后续直接写数据库
        parsed = {
            "resolution": float(raw_data["resolution"]),
            "origin_x": float(origin[0]),
            "origin_y": float(origin[1]),
            "origin_yaw": float(origin[2]),
            "negate": int(raw_data.get("negate", 0)),
            "occupied_thresh": float(raw_data.get("occupied_thresh", 0.65)),
            "free_thresh": float(raw_data.get("free_thresh", 0.196)),
        }
        if parsed["free_thresh"] >= parsed["occupied_thresh"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="YAML 中 free_thresh 必须小于 occupied_thresh"
            )
        return parsed
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="YAML 中的 resolution/origin 必须是数值"
        ) from exc


def world_to_pixel(origin_x: float, origin_y: float, origin_yaw: float, resolution: float, width: int, height: int) -> tuple[int, int]:
    # 把世界坐标中的 (0, 0) 点，反推出它在地图图片中的像素位置
    # 这一步主要是为了在预览图上给“世界坐标原点”画一个醒目的标记
    dx = -origin_x
    dy = -origin_y

    cos_yaw = np.cos(origin_yaw)
    sin_yaw = np.sin(origin_yaw)

    map_x = (dx * cos_yaw + dy * sin_yaw) / resolution
    map_y = (-dx * sin_yaw + dy * cos_yaw) / resolution

    pixel_x = int(round(map_x))
    pixel_y = int(round(height - map_y))
    return pixel_x, pixel_y


def add_origin_marker(
    preview_image: Image.Image,
    yaml_meta: dict[str, float],
    original_width: int,
    original_height: int,
    offset_x: int = 0,
    offset_y: int = 0,
) -> None:
    # 如果世界坐标原点落在地图范围内，就在预览图上画一个红色十字标记
    # 注意：预览图可能已经裁剪过，所以需要减掉裁剪偏移量
    pixel_x, pixel_y = world_to_pixel(
        yaml_meta["origin_x"],
        yaml_meta["origin_y"],
        yaml_meta["origin_yaw"],
        yaml_meta["resolution"],
        original_width,
        original_height,
    )
    pixel_x -= offset_x
    pixel_y -= offset_y

    width, height = preview_image.size

    if not (0 <= pixel_x < width and 0 <= pixel_y < height):
        return

    marker_half = max(6, min(width, height) // 60)
    draw = ImageDraw.Draw(preview_image)
    draw.line((pixel_x - marker_half, pixel_y, pixel_x + marker_half, pixel_y), fill=(225, 29, 72), width=2)
    draw.line((pixel_x, pixel_y - marker_half, pixel_x, pixel_y + marker_half), fill=(225, 29, 72), width=2)
    draw.ellipse(
        (pixel_x - 3, pixel_y - 3, pixel_x + 3, pixel_y + 3),
        fill=(255, 255, 255),
        outline=(225, 29, 72),
        width=2,
    )


def extract_primary_region_mask(known_mask: np.ndarray) -> np.ndarray:
    # 目标：只保留地图主体附近的区域，把外围大量射线状毛刺和零散噪声排除掉
    # 步骤：
    # 1. 开运算去掉细碎噪声和很细的毛刺
    # 2. 闭运算把主体区域连接得更完整
    # 3. 填洞得到一个比较连贯的主体轮廓
    # 4. 只取最大连通区域，忽略外围零散扫描区域
    # 5. 适度膨胀，给边界留出缓冲空间
    min_dim = min(known_mask.shape)

    def odd_size(value: int) -> int:
        return value if value % 2 == 1 else value + 1

    open_size = odd_size(max(3, min_dim // 180))
    close_size = odd_size(max(11, min_dim // 32))
    dilate_size = odd_size(max(9, min_dim // 40))

    opened = ndimage.binary_opening(known_mask, structure=np.ones((open_size, open_size), dtype=bool))
    closed = ndimage.binary_closing(opened, structure=np.ones((close_size, close_size), dtype=bool))
    filled = ndimage.binary_fill_holes(closed)

    # 某些类型检查器会把 ndimage.label 误推断为“仅返回一个整数”，
    # 这里显式收窄为 (labeled_array, num_features) 以避免误报。
    labeled, count = cast(tuple[np.ndarray, int], ndimage.label(filled))
    if count == 0:
        return known_mask

    component_sizes = np.bincount(labeled.ravel())
    component_sizes[0] = 0
    largest_component = int(component_sizes.argmax())
    primary_region = labeled == largest_component
    return ndimage.binary_dilation(primary_region, structure=np.ones((dilate_size, dilate_size), dtype=bool))


def compute_crop_box(primary_region_mask: np.ndarray, width: int, height: int) -> tuple[int, int, int, int]:
    coords = np.argwhere(primary_region_mask)
    if coords.size == 0:
        return 0, 0, width, height

    top = int(coords[:, 0].min())
    bottom = int(coords[:, 0].max()) + 1
    left = int(coords[:, 1].min())
    right = int(coords[:, 1].max()) + 1

    padding = max(30, min(width, height) // 35)
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


def generate_preview_and_dimensions(pgm_path: Path, preview_path: Path, yaml_meta: dict[str, float]) -> dict[str, int]:
    # 读取 .pgm 地图文件，并生成一张更适合人眼查看的 PNG 预览图
    # 这里不再简单保留灰度，而是结合 YAML 里的阈值，把地图语义分成：
    # - 可通行区域
    # - 未知区域
    # - 障碍物区域
    try:
        with Image.open(pgm_path) as img:
            grayscale = img.convert("L")
            width, height = grayscale.size

            pixels = np.array(grayscale, dtype=np.uint8)

            # ROS 地图里，occupancy 值的方向可能会被 negate 影响：
            # negate = 0: 像素越黑，越像障碍物
            # negate = 1: 像素越白，越像障碍物
            if int(yaml_meta["negate"]) == 1:
                occupancy = pixels.astype(np.float32) / 255.0
            else:
                occupancy = (255.0 - pixels.astype(np.float32)) / 255.0

            occupied_thresh = float(yaml_meta["occupied_thresh"])
            free_thresh = float(yaml_meta["free_thresh"])

            occupied_mask = occupancy >= occupied_thresh
            free_mask = occupancy <= free_thresh
            unknown_mask = ~(occupied_mask | free_mask)
            known_mask = free_mask | occupied_mask
            primary_region_mask = extract_primary_region_mask(known_mask)
            crop_left, crop_top, crop_right, crop_bottom = compute_crop_box(primary_region_mask, width, height)

            # 做一张 RGB 彩色预览图，让三类区域更容易区分：
            # 可通行区域：浅米白
            # 未知区域：中性灰蓝
            # 障碍物区域：深青黑
            color_preview = np.zeros((height, width, 3), dtype=np.uint8)
            color_preview[free_mask] = (244, 241, 232)
            color_preview[unknown_mask] = (176, 184, 192)
            color_preview[occupied_mask] = (28, 49, 45)

            # 主区域外的颜色统一收敛成更轻的背景色，弱化外围噪声
            color_preview[~primary_region_mask] = (233, 238, 241)

            cropped_preview = color_preview[crop_top:crop_bottom, crop_left:crop_right]
            preview_image = Image.fromarray(cropped_preview, mode="RGB")
            add_origin_marker(
                preview_image,
                yaml_meta,
                original_width=width,
                original_height=height,
                offset_x=crop_left,
                offset_y=crop_top,
            )
            preview_image.save(preview_path, format="PNG")
            return {
                "width": width,
                "height": height,
                "preview_width": crop_right - crop_left,
                "preview_height": crop_bottom - crop_top,
                "preview_offset_x": crop_left,
                "preview_offset_y": crop_top,
            }
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PGM 文件无法解析: {exc}"
        ) from exc


def to_relative_upload_path(path: Path) -> str:
    # 数据库里不存绝对路径，只存相对于 uploads/ 的路径
    # 这样路径在不同机器上更容易迁移
    return path.relative_to(UPLOAD_ROOT).as_posix()


def remove_map_directory(folder_name: str) -> None:
    # 上传过程中如果出错，就把刚刚创建的整张地图目录一起删掉
    # 避免磁盘上残留“只上传了一半”的脏文件
    if not folder_name:
        return
    shutil.rmtree(MAPS_ROOT / folder_name, ignore_errors=True)


def remove_map_files_by_relative_path(relative_path: str) -> None:
    # 删除地图时，数据库里只有相对路径
    # 这里先把相对路径恢复成磁盘绝对路径，再删除所在文件夹
    if not relative_path:
        return

    target = (UPLOAD_ROOT / relative_path).resolve()
    upload_root = UPLOAD_ROOT.resolve()

    # 额外做一层保护，确保删除操作只会发生在 uploads 目录内部
    if upload_root not in target.parents and target != upload_root:
        return

    folder = target.parent
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
