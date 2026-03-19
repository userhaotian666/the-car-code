import asyncio # 【新增】导入 asyncio 用于创建后台任务
from fastapi import FastAPI
from contextlib import asynccontextmanager
from database import engine, Base
from fastapi.middleware.cors import CORSMiddleware

from routers import devices, car, map, mission, history, path, task, problem, command
from service import start_scheduler, scheduler

# 【新增】导入你分出来的 MQTT 监听协程
# 假设你按照之前的建议，把它放在了 mqtt 文件夹下的 client.py 中
from MQTT import mqtt_listener 

# --- 1. 使用 lifespan 管理启动和关闭 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 服务启动阶段 ---
    async with engine.begin() as conn:
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