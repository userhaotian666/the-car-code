import asyncio  # 👈 替换 time
import random
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession # 👈 替换 Session
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# ================= 📦 依赖引入 =================
from database import AsyncSessionLocal
from model import Task, Car, CarHistory, Problem, Path

# ================= ⚙️ 仿真参数配置 =================
SIMULATION_INTERVAL = 2.0
MOVE_SPEED_RATIO = 0.05
BATTERY_CONSUMPTION = 0.2
FAULT_PROBABILITY = 0.00
AMBIENT_TEMP = 25.0
MAX_TEMP = 95.0
HEATING_RATE = 1.5
COOLING_RATE = 2.0

# 状态常量
TASK_RUNNING = 1
TASK_COMPLETED = 3
CAR_FAULT = 0
CAR_STANDBY = 1
CAR_RUNNING = 2

class VirtualCarDriver:
    def __init__(self, car_id: int):
        self.car_id = car_id
        self.current_path_index = 0
        self.segment_progress = 0.0
        self.current_lat = 0.0
        self.current_lng = 0.0
        self.is_initialized = False
        self.current_battery = 100.0 
        self.current_temp = AMBIENT_TEMP
        self.current_speed = 0.0          
        self.current_signal = 100         
        self.triggered_milestones = set()

    async def run_step(self, db: AsyncSession): # 👈 改为 async def
        """执行单步模拟"""
        
        # 1. 异步获取车辆及其当前任务 (使用 selectinload 预加载任务和路径)
        stmt = (
            select(Car)
            .options(selectinload(Car.current_task).selectinload(Task.path_info))
            .where(Car.id == self.car_id)
        )
        result = await db.execute(stmt)
        car = result.scalars().first()
        
        if not car:
            print(f"❌ 找不到车辆 ID {self.car_id}")
            return

        task = car.current_task
        
        # 2. 初始化位置
        if not self.is_initialized and task and task.path_info:
             waypoints = task.path_info.waypoints
             if waypoints:
                self.current_lat = waypoints[0]["lat"]
                self.current_lng = waypoints[0]["lng"]
                self.is_initialized = True

        # 3. 随机故障检测
        if car.status != CAR_FAULT and random.random() < FAULT_PROBABILITY:
            print(f"💥 警告！车辆 {self.car_id} 突发随机故障！")
            car.status = CAR_FAULT
            await db.commit() # 👈 await

        # 4. 电量耗尽检测
        if self.current_battery <= 0:
            self.current_battery = 0
            if car.status != CAR_FAULT:
                print(f"🪫 警告！车辆 {self.car_id} 电量耗尽！")
                car.status = CAR_FAULT 
                await db.commit()

        # 5. 决策：车辆是否应该移动
        is_healthy = (car.status != CAR_FAULT) and (self.current_battery > 0)
        has_task = (task is not None) and (task.path_info is not None)
        should_move = has_task and (task.status == TASK_RUNNING) and (car.status == CAR_RUNNING) and is_healthy

        # 🌡️ ⚡ 📶 物理仿真计算 (保持逻辑不变)
        if should_move:
            self.current_temp += HEATING_RATE + random.uniform(-0.2, 0.8)
            target_speed = random.uniform(5.0, 15.0)
            self.current_speed = (self.current_speed * 0.8) + (target_speed * 0.2)
        else:
            self.current_temp -= COOLING_RATE
            self.current_speed = 0.0
        
        self.current_temp = max(AMBIENT_TEMP, min(self.current_temp, MAX_TEMP))
        self.current_signal = max(0, min(100, int(random.gauss(85, 10))))

        # 🚀 移动逻辑与里程碑检测
        if should_move:
            self.current_battery -= BATTERY_CONSUMPTION
            # 👈 调用异步移动方法
            await self._move_and_check_events(task.path_info.waypoints, db, task, car)
            
            print(f"🚗 行驶 | 进度:{self.current_path_index}/{len(task.path_info.waypoints)} | "
                  f"速度:{self.current_speed:.1f}m/s | 温:{self.current_temp:.1f}℃")
        else:
            print(f"⏸️ 静止 | 电量:{int(self.current_battery)}% | 温:{self.current_temp:.1f}℃")

        # 💾 写入 CarHistory (异步添加)
        history_record = CarHistory(
            car_id=self.car_id,
            battery=int(self.current_battery),
            longitude=self.current_lng,
            latitude=self.current_lat,
            car_status=car.status,
            reported_at=datetime.now(),
            temperature=round(self.current_temp, 1),
            speed=round(self.current_speed, 1),
            signal=self.current_signal
        )
        db.add(history_record)
        await db.commit() # 👈 await

    async def _move_and_check_events(self, waypoints, db: AsyncSession, task: Task, car: Car):
        """处理移动逻辑（异步版）"""
        total_points = len(waypoints)
        if total_points < 2: return

        if self.current_path_index >= total_points - 1:
            task.status = TASK_COMPLETED
            task.finished_at = datetime.now()
            car.status = CAR_STANDBY
            car.current_task_id = None
            self.triggered_milestones.clear()
            self.current_path_index = 0
            self.segment_progress = 0.0
            self.is_initialized = False
            await db.commit()
            return
        
        # 位置插值计算
        start_pt = waypoints[self.current_path_index]
        end_pt = waypoints[self.current_path_index + 1]
        self.segment_progress += MOVE_SPEED_RATIO

        if self.segment_progress >= 1.0:
            self.segment_progress = 0.0
            self.current_path_index += 1
            self.current_lat = end_pt["lat"]
            self.current_lng = end_pt["lng"]
        else:
            self.current_lat = start_pt["lat"] + (end_pt["lat"] - start_pt["lat"]) * self.segment_progress
            self.current_lng = start_pt["lng"] + (end_pt["lng"] - start_pt["lng"]) * self.segment_progress

        # 里程碑检测
        current_progress = self.current_path_index / (total_points - 1)
        milestone_rules = [
            (0.25, "轮胎异常", "左前轮胎压监测数值波动异常。"),
            (0.50, "电池高温", "电池组核心温度略微升高。"),
            (0.75, "信号干扰", "进入弱信号区域。")
        ]

        for threshold, name, desc in milestone_rules:
            if current_progress >= threshold and threshold not in self.triggered_milestones:
                print(f"⚠️ [触发问题]: {name}")
                self.triggered_milestones.add(threshold)
                new_problem = Problem(
                    task_id=task.id,
                    name=name,
                    description=f"{desc} (坐标: {self.current_lat:.4f}, {self.current_lng:.4f})"
                )
                db.add(new_problem)
                await db.commit() # 👈 立即提交

async def start_simulation(target_car_id: int): # 👈 改为 async def
    print(f"🚀 启动异步仿真引擎 (ID: {target_car_id})")
    driver = VirtualCarDriver(target_car_id)
    
    while True:
        # 使用 async with 管理异步会话
        async with AsyncSessionLocal() as db:
            try:
                await driver.run_step(db)
            except Exception as e:
                print(f"❌ 仿真异常: {e}")
        
        # 👈 使用 asyncio.sleep 而不是 time.sleep
        await asyncio.sleep(SIMULATION_INTERVAL)

if __name__ == "__main__":
    # 使用 asyncio 运行入口
    try:
        asyncio.run(start_simulation(target_car_id=2))
    except KeyboardInterrupt:
        print("停止仿真")