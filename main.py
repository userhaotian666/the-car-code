import asyncio # 【新增】导入 asyncio 用于创建后台任务
from pathlib import Path
from fastapi import FastAPI
from contextlib import asynccontextmanager
from database import engine, Base
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect

from routers import devices, car, map, mission, history, path, task, problem, command
from service import start_scheduler, scheduler
from map_storage import ensure_storage_root
from model import CarHistory, Map

# 【新增】导入你分出来的 MQTT 监听协程
# 假设你按照之前的建议，把它放在了 mqtt 文件夹下的 client.py 中
from MQTT import mqtt_listener 

# --- 1. 使用 lifespan 管理启动和关闭 ---
def validate_map_table_schema(sync_conn) -> None:
    # create_all 只会“补不存在的表”，不会自动把旧表改成新结构。
    # 所以这里先检查 maps 表是不是已经换成了新的地图文件结构。
    # 如果还是旧的 center_lat / center_lng / zoom 结构，就直接报错提醒手动重建
    inspector = inspect(sync_conn)
    if "maps" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("maps")}
    expected_columns = {column.name for column in Map.__table__.columns}

    if existing_columns != expected_columns:
        raise RuntimeError(
            "检测到 maps 表仍是旧结构或结构不匹配。请先手动删除或重建 maps 表，再重新启动服务。"
        )


def validate_car_history_table_schema(sync_conn) -> None:
    inspector = inspect(sync_conn)
    if "car_history" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("car_history")}
    expected_columns = {column.name for column in CarHistory.__table__.columns}
    missing_columns = sorted(expected_columns - existing_columns)

    if not missing_columns:
        return

    sql_statements = []
    if "yaw" in missing_columns:
        sql_statements.append(
            "ALTER TABLE car_history ADD COLUMN yaw FLOAT NULL COMMENT '相对地图原点的朝向(度)';"
        )
    if "mode" in missing_columns:
        sql_statements.append(
            "ALTER TABLE car_history ADD COLUMN mode SMALLINT NULL COMMENT '模式: 1-遥控, 2-自主导航';"
        )
    if "work_status" in missing_columns:
        sql_statements.append(
            "ALTER TABLE car_history ADD COLUMN work_status SMALLINT NULL COMMENT '小车工作状态';"
        )

    sql_hint = "\n".join(sql_statements) if sql_statements else "请根据最新模型手动补齐 car_history 缺失列。"
    raise RuntimeError(
        "检测到 car_history 表缺少字段: "
        f"{', '.join(missing_columns)}。\n"
        "请先执行以下 SQL 更新数据库后再重新启动服务：\n"
        f"{sql_hint}"
    )


def validate_car_table_schema(sync_conn) -> None:
    inspector = inspect(sync_conn)
    if "cars" not in inspector.get_table_names():
        return

    columns = inspector.get_columns("cars")
    existing_columns = {column["name"] for column in columns}
    if "ip_address" not in existing_columns:
        raise RuntimeError(
            "检测到 cars 表缺少字段: ip_address。\n"
            "请先执行以下 SQL 更新数据库后再重新启动服务：\n"
            "ALTER TABLE cars ADD COLUMN ip_address VARCHAR(45) NULL COMMENT '小车IP地址';\n"
            "-- 为现有车辆补齐唯一 IP 后，再执行：\n"
            "ALTER TABLE cars MODIFY COLUMN ip_address VARCHAR(45) NOT NULL COMMENT '小车IP地址';\n"
            "CREATE UNIQUE INDEX uq_cars_ip_address ON cars (ip_address);"
        )

    ip_column = next((column for column in columns if column["name"] == "ip_address"), None)
    if ip_column and ip_column.get("nullable", True):
        raise RuntimeError(
            "检测到 cars.ip_address 仍允许为空。\n"
            "请先执行以下 SQL 更新数据库后再重新启动服务：\n"
            "ALTER TABLE cars MODIFY COLUMN ip_address VARCHAR(45) NOT NULL COMMENT '小车IP地址';"
        )

    unique_constraints = inspector.get_unique_constraints("cars")
    unique_indexes = inspector.get_indexes("cars")
    has_ip_unique = any(constraint.get("column_names") == ["ip_address"] for constraint in unique_constraints) or any(
        index.get("unique") and index.get("column_names") == ["ip_address"] for index in unique_indexes
    )

    if not has_ip_unique:
        raise RuntimeError(
            "检测到 cars.ip_address 尚未建立唯一约束。\n"
            "请先执行以下 SQL 更新数据库后再重新启动服务：\n"
            "CREATE UNIQUE INDEX uq_cars_ip_address ON cars (ip_address);"
        )

    if "work_status" not in existing_columns:
        raise RuntimeError(
            "检测到 cars 表缺少字段: work_status。\n"
            "请先执行以下 SQL 更新数据库后再重新启动服务：\n"
            "ALTER TABLE cars ADD COLUMN work_status SMALLINT NULL COMMENT '车辆工作状态';"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 服务启动阶段 ---
    async with engine.begin() as conn:
        await conn.run_sync(validate_map_table_schema)
        await conn.run_sync(validate_car_history_table_schema)
        await conn.run_sync(validate_car_table_schema)
        # run_sync 是关键，它允许在异步连接中执行同步的 SQLAlchemy 命令
        await conn.run_sync(Base.metadata.create_all)
    
    await start_scheduler()
    
    # 【新增】将 MQTT 监听器作为一个独立的后台任务启动
    mqtt_task = asyncio.create_task(mqtt_listener())
    
    yield
    
    # --- 服务关闭阶段 ---
    scheduler.shutdown()
    
    # 【新增】优雅地关闭 MQTT 监听任务
    mqtt_task.cancel()
    try:
        await mqtt_task
    except asyncio.CancelledError:
        print("🛑 MQTT 监听任务已安全停止")

# --- 2. 初始化 App ---
app = FastAPI(lifespan=lifespan)

# 启动时先确保 uploads/maps 目录存在
# 然后把整个 uploads 目录作为静态文件目录挂到 /static
# 这样数据库里存的相对路径就能被前端通过 URL 访问到
ensure_storage_root()
static_root = Path(__file__).resolve().parent / "uploads"
app.mount("/static", StaticFiles(directory=str(static_root)), name="static")

# --- 3. 中间件配置 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 4. 注册路由 ---
app.include_router(devices.router)
app.include_router(car.router)
app.include_router(map.router)
app.include_router(mission.router)
app.include_router(history.router)
app.include_router(path.router)
app.include_router(task.router)
app.include_router(problem.router)
app.include_router(command.router)

# --- 5. 根路由 ---
@app.get("/")
async def root():
    return {"message": "Server is running in async mode with Scheduler and MQTT!"}
