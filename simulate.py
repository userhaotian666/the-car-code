import time
import random
from datetime import datetime
from sqlalchemy.orm import Session

# 引入你的项目依赖
from database import SessionLocal
from model import Task, Car, CarHistory

# ================= ⚙️ 仿真参数配置 =================
SIMULATION_INTERVAL = 1.0       # 刷新频率 (秒)
MOVE_SPEED_RATIO = 0.1          # 移动速度 (每秒走两点间距离的 10%)

# --- 新增配置 ---
BATTERY_CONSUMPTION = 0.5       # 耗电速率 (每秒消耗 0.5% 电量)
FAULT_PROBABILITY = 0.01        # 故障概率 (每秒 1% 的几率发生随机故障)
# =================================================

# 状态常量
TASK_RUNNING = 1
TASK_PAUSED = 2
TASK_COMPLETED = 3

CAR_FAULT = 0
CAR_STANDBY = 1
CAR_RUNNING = 2

class VirtualCarDriver:
    def __init__(self, car_id: int):
        self.car_id = car_id
        
        # 路径相关状态
        self.current_path_index = 0
        self.segment_progress = 0.0
        self.current_lat = 0.0
        self.current_lng = 0.0
        self.is_initialized = False
        
        # 【新增】电量状态 (初始 100%)
        self.current_battery = 100.0 

    def run_step(self, db: Session):
        """执行单步模拟"""
        
        # 1. 获取小车
        car = db.get(Car, self.car_id)
        if car is None:
            print(f"❌ 找不到车辆 ID {self.car_id}，停止模拟")
            return

        # 2. 获取任务
        task = car.current_task
        if task is None or task.path_info is None:
            if not self.is_initialized:
                # 如果没任务，电量可以缓慢自动恢复(充电)或者保持不变，这里假设保持不变
                print(f"💤 车辆 {self.car_id} 待机中... 电量: {int(self.current_battery)}%")
            return

        waypoints = task.path_info.waypoints
        if not waypoints or len(waypoints) < 2:
            return

        # --- 初始化位置 ---
        if not self.is_initialized:
            self.current_lat = waypoints[0]["lat"]
            self.current_lng = waypoints[0]["lng"]
            self.is_initialized = True

        # =========================================================
        # 🔥 【新增逻辑 1】随机故障模拟
        # 只有在车是好的时候才判定是否发生故障
        # =========================================================
        if car.status != CAR_FAULT and random.random() < FAULT_PROBABILITY:
            print(f"💥 警告！车辆 {self.car_id} 突发引擎故障！")
            car.status = CAR_FAULT
            db.commit() # 立即写入数据库，导致下面 should_move 变为 False
            
        # =========================================================
        # 🔥 【新增逻辑 2】没电逻辑
        # =========================================================
        if self.current_battery <= 0:
            self.current_battery = 0
            if car.status != CAR_FAULT:
                print(f"🪫 警告！车辆 {self.car_id} 电量耗尽，停止运行！")
                # 电量耗尽也视为一种故障，或者你可以定义一个新的状态
                car.status = CAR_FAULT 
                db.commit()

        # 3. 判断是否移动
        # 增加条件：只有电量 > 0 且 没故障 才能动
        is_healthy = (car.status != CAR_FAULT) and (self.current_battery > 0)
        should_move = (task.status == TASK_RUNNING) and (car.status == CAR_RUNNING) and is_healthy

        if should_move:
            # 只有移动时才耗电
            self.current_battery -= BATTERY_CONSUMPTION
            if self.current_battery < 0: self.current_battery = 0
            
            self._move_forward(waypoints, db, task)
        else:
            # 打印详细状态原因
            reason = "未知"
            if car.status == CAR_FAULT: reason = "故障/没电"
            elif task.status == TASK_PAUSED: reason = "任务暂停"
            elif car.status == CAR_STANDBY: reason = "待机"
            
            print(f"⏸️ 车辆 {self.car_id} 静止 [{reason}] - 电量: {int(self.current_battery)}% - 位置: {self.current_lat:.6f}, {self.current_lng:.6f}")

        # 4. 写入历史表 (使用真实的 current_battery)
        history_record = CarHistory(
            car_id=self.car_id,
            battery=int(self.current_battery), # 转为整数存入数据库
            longitude=self.current_lng,
            latitude=self.current_lat,
            car_status=car.status,
            reported_at=datetime.now()
        )
        db.add(history_record)
        db.commit()

    def _move_forward(self, waypoints, db: Session, task):
        # ... (这部分逻辑和之前一样，无需改动) ...
        # 判断终点
        if self.current_path_index >= len(waypoints) - 1:
            print(f"✅ 车辆 {self.car_id} 到达终点！任务完成。")
            task.status = TASK_COMPLETED
            task.finished_at = datetime.now()
            
            car = db.get(Car, self.car_id)
            if car:
                car.status = CAR_STANDBY
                car.current_task_id = None
                # 任务完成后，可以在这里把电量回满，或者留着下次继续用
                # self.current_battery = 100.0 
            
            db.commit()
            
            self.current_path_index = 0
            self.segment_progress = 0.0
            self.is_initialized = False
            return

        # 插值移动
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

        print(f"🚗 车辆 {self.car_id} 行驶中... 电量:{int(self.current_battery)}% 进度:{self.current_path_index}/{len(waypoints)}")

def start_simulation(target_car_id: int):
    print(f"🚀 启动仿真 (ID: {target_car_id}) | 耗电率: {BATTERY_CONSUMPTION}%/s | 故障率: {FAULT_PROBABILITY*100}%")
    driver = VirtualCarDriver(target_car_id)
    
    while True:
        db = SessionLocal()
        try:
            driver.run_step(db)
        except Exception as e:
            print(f"❌ 仿真异常: {e}")
        finally:
            db.close()
        
        time.sleep(SIMULATION_INTERVAL)

if __name__ == "__main__":
    start_simulation(target_car_id=9)