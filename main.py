from fastapi import FastAPI
from database import engine, Base
from routers import devices,car

# 创建数据库表（如果表不存在）
Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- 核心步骤：注册路由 ---
# 这就像把插线板插到墙上
app.include_router(devices.router)
app.include_router(car.router)

@app.get("/")
def root():
    return {"message": "Server is running!"}