from fastapi import FastAPI
from contextlib import asynccontextmanager
from database import engine, Base
from routers import devices, car, map, mission, history, path, task, problem
from fastapi.middleware.cors import CORSMiddleware

# --- 1. 使用 lifespan 管理启动和关闭 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 【启动时执行】：异步创建数据库表
    async with engine.begin() as conn:
        # run_sync 是关键，它允许在异步连接中执行同步的 SQLAlchemy 命令
        await conn.run_sync(Base.metadata.create_all)
    
    yield  # 这里是应用运行的阶段
    
    # 【关闭时执行】：可以在这里写清理逻辑，比如关闭数据库连接池
    await engine.dispose()

# --- 2. 初始化 App，并传入 lifespan ---
app = FastAPI(lifespan=lifespan)

# --- 3. 中间件配置（保持不变） ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 4. 注册路由（保持不变） ---
app.include_router(devices.router)
app.include_router(car.router)
app.include_router(map.router)
app.include_router(mission.router)
app.include_router(history.router)
app.include_router(path.router)
app.include_router(task.router)
app.include_router(problem.router)

# --- 5. 根路由建议改为 async ---
@app.get("/")
async def root():
    return {"message": "Server is running in async mode!"}