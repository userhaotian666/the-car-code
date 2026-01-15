from fastapi import FastAPI
from database import engine, Base
from routers import devices,car,map,mission,history,path,task
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
# 创建数据库表（如果表不存在）
Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    # 允许的来源：生产环境请换成具体的 ["http://192.168.31.56:8000/devices/"]
    # 开发环境为了方便，直接用 ["*"] 表示允许任何 IP 访问
    allow_origins=["*"], 
    allow_credentials=True,
    # 允许的方法：GET, POST, PUT, DELETE 等
    allow_methods=["*"],
    # 允许的 Header
    allow_headers=["*"],
)

# --- 核心步骤：注册路由 ---
# 这就像把插线板插到墙上
app.include_router(devices.router)
app.include_router(car.router)
app.include_router(map.router)
app.include_router(mission.router)
app.include_router(history.router)
app.include_router(path.router)
app.include_router(task.router)

@app.get("/")
def root():
    return {"message": "Server is running!"}