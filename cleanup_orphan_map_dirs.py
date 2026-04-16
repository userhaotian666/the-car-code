from __future__ import annotations

import argparse
import asyncio
import shutil
from pathlib import Path

from sqlalchemy import select

from database import AsyncSessionLocal
from map_storage import MAPS_ROOT, UPLOAD_ROOT, ensure_storage_root
from model import Map


def extract_map_folder_name(relative_path: str | None) -> str | None:
    """
    从数据库里存的相对路径中提取地图目录名。

    例如：
    maps/abc123/map.pgm -> abc123
    """
    if not relative_path:
        return None

    path = Path(relative_path)
    parts = path.parts
    if len(parts) < 3:
        return None
    if parts[0] != "maps":
        return None
    return parts[1]


async def fetch_active_map_folders() -> set[str]:
    """
    查询数据库中仍然被地图记录引用的目录名。
    """
    active_folders: set[str] = set()

    async with AsyncSessionLocal() as db:
        stmt = select(Map.pgm_path, Map.yaml_path, Map.preview_path)
        result = await db.execute(stmt)

        for pgm_path, yaml_path, preview_path in result.all():
            for relative_path in (pgm_path, yaml_path, preview_path):
                folder_name = extract_map_folder_name(relative_path)
                if folder_name:
                    active_folders.add(folder_name)

    return active_folders


def collect_disk_map_folders() -> set[str]:
    """
    扫描 uploads/maps 目录下实际存在的一级子目录。
    """
    ensure_storage_root()
    if not MAPS_ROOT.exists():
        return set()

    return {path.name for path in MAPS_ROOT.iterdir() if path.is_dir()}


def remove_folders(folder_names: set[str]) -> list[Path]:
    """
    真正删除磁盘上的孤儿地图目录。
    """
    removed_paths: list[Path] = []
    upload_root = UPLOAD_ROOT.resolve()

    for folder_name in sorted(folder_names):
        target = (MAPS_ROOT / folder_name).resolve()

        # 额外防护：只允许删除 uploads/maps 下面的目录
        if upload_root not in target.parents:
            continue

        if target.exists() and target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            removed_paths.append(target)

    return removed_paths


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="清理 uploads/maps 中数据库已无记录引用的孤儿地图目录"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正执行删除。默认仅预览，不删除任何文件。",
    )
    args = parser.parse_args()

    active_folders = await fetch_active_map_folders()
    disk_folders = collect_disk_map_folders()

    orphan_folders = disk_folders - active_folders
    missing_folders = active_folders - disk_folders

    print("=== 地图目录清理报告 ===")
    print(f"数据库引用目录数量: {len(active_folders)}")
    print(f"磁盘实际目录数量: {len(disk_folders)}")
    print(f"孤儿目录数量: {len(orphan_folders)}")
    print(f"数据库存在但磁盘缺失数量: {len(missing_folders)}")

    if missing_folders:
        print("\n数据库中存在但磁盘缺失的目录:")
        for folder_name in sorted(missing_folders):
            print(f"  - {folder_name}")

    if not orphan_folders:
        print("\n没有发现需要清理的孤儿地图目录。")
        return

    print("\n孤儿地图目录:")
    for folder_name in sorted(orphan_folders):
        print(f"  - {MAPS_ROOT / folder_name}")

    if not args.apply:
        print("\n当前是预览模式，未删除任何文件。")
        print("如需真正删除，请执行: python3 cleanup_orphan_map_dirs.py --apply")
        return

    removed_paths = remove_folders(orphan_folders)
    print(f"\n已删除 {len(removed_paths)} 个孤儿地图目录。")
    for path in removed_paths:
        print(f"  - {path}")


if __name__ == "__main__":
    asyncio.run(main())
