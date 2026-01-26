import time
import random
from datetime import datetime
from sqlalchemy.orm import Session

# ================= 📦 依赖引入 =================
# 请确保这些文件在同一目录下，或者在 Python 路径中
from database import SessionLocal
from model import Task, Car, CarHistory, Problem, Path

# ================= ⚙️ 仿真参数配置 =================
SIMULATION_INTERVAL = 2.0       # 刷新频率 (秒)
MOVE_SPEED_RATIO = 0.05         # 移动步长 (每秒走两点间距离的 5%，调小一点可以让车跑慢点，更容易观察到里程碑)

BATTERY_CONSUMPTION = 0.2       # 耗电速率 (%/s)
FAULT_PROBABILITY = 0.00        # 随机故障概率 (设为 0 以便专门测试里程碑故障)

# --- 环境仿真参数 ---
AMBIENT_TEMP = 25.0             # 环境温度
MAX_TEMP = 95.0                 # 最高引擎温度
HEATING_RATE = 1.5              # 运行时升温速率
COOLING_RATE = 2.0              # 停机时冷却速率
# =================================================

# 状态常量 (需与数据库定义一致)
TASK_RUNNING = 1
TASK_PAUSED = 2
TASK_COMPLETED = 3

CAR_FAULT = 0
CAR_STANDBY = 1
CAR_RUNNING = 2

class VirtualCarDriver:
    def __init__(self, car_id: int):
        self.car_id = car_id
        
        # --- 路径导航状态 ---
        self.current_path_index = 0
        self.segment_progress = 0.0
        self.current_lat = 0.0
        self.current_lng = 0.0
        self.is_initialized = False
        
        # --- 车辆物理状态 ---
        self.current_battery = 100.0 
        self.current_temp = AMBIENT_TEMP
        self.current_speed = 0.0          
        self.current_signal = 100         

        # --- 🔥 关键：记录已触发的里程碑 ---
        # 格式: {0.25, 0.5, 0.75}，防止重复报错
        self.triggered_milestones = set()

    def run_step(self, db: Session):
        """执行单步模拟"""
        
        # 1. 获取车辆和当前任务
        car = db.get(Car, self.car_id)
        if not car:
            print(f"❌ 找不到车辆 ID {self.car_id}")
            return

        task = car.current_task
        
        # 2. 初始化位置 (如果还没定位)
        if not self.is_initialized and task and task.path_info:
             waypoints = task.path_info.waypoints
             if waypoints:
                self.current_lat = waypoints[0]["lat"]
                self.current_lng = waypoints[0]["lng"]
                self.is_initialized = True

        # 3. 随机故障检测 (引擎爆炸等)
        if car.status != CAR_FAULT and random.random() < FAULT_PROBABILITY:
            print(f"💥 警告！车辆 {self.car_id} 突发随机故障！")
            car.status = CAR_FAULT
            db.commit()

        # 4. 电量耗尽检测
        if self.current_battery <= 0:
            self.current_battery = 0
            if car.status != CAR_FAULT:
                print(f"🪫 警告！车辆 {self.car_id} 电量耗尽！")
                car.status = CAR_FAULT 
                db.commit()

        # 5. 决策：车辆是否应该移动
        is_healthy = (car.status != CAR_FAULT) and (self.current_battery > 0)
        has_task = (task is not None) and (task.path_info is not None)
        should_move = has_task and (task.status == TASK_RUNNING) and (car.status == CAR_RUNNING) and is_healthy

        # =========================================
        # 🌡️ ⚡ 📶 物理环境仿真计算
        # =========================================
        
        # A. 温度模拟
        if should_move:
            self.current_temp += HEATING_RATE + random.uniform(-0.2, 0.8)
        else:
            self.current_temp -= COOLING_RATE
        self.current_temp = max(AMBIENT_TEMP, min(self.current_temp, MAX_TEMP))

        # B. 速度模拟 (m/s)
        if should_move:
            target_speed = random.uniform(5.0, 15.0) # 目标速度 5~15 m/s
            self.current_speed = (self.current_speed * 0.8) + (target_speed * 0.2) # 平滑处理
        else:
            self.current_speed = 0.0

        # C. 信号模拟 (0-100)
        self.current_signal = int(random.gauss(85, 10))
        self.current_signal = max(0, min(100, self.current_signal))

        # =========================================
        # 🚀 移动逻辑与里程碑检测
        # =========================================
        if should_move:
            self.current_battery -= BATTERY_CONSUMPTION
            if self.current_battery < 0: self.current_battery = 0
            
            # 执行移动，并传入 DB 和 Task 以便记录 Problem
            self._move_and_check_events(task.path_info.waypoints, db, task)
            
            print(f"🚗 行驶 | 进度:{self.current_path_index}/{len(task.path_info.waypoints)} | "
                  f"速度:{self.current_speed:.1f}m/s | 温:{self.current_temp:.1f}℃")
        else:
            if has_task and task.status == TASK_COMPLETED:
                print(f"✅ 任务完成 | 冷却中... {self.current_temp:.1f}℃")
            else:
                reason = "待机"
                if car.status == CAR_FAULT: reason = "故障"
                elif task and task.status == TASK_PAUSED: reason = "暂停"
                print(f"⏸️ 静止[{reason}] | 电量:{int(self.current_battery)}% | 温:{self.current_temp:.1f}℃")

        # =========================================
        # 💾 写入 CarHistory (实时状态)
        # =========================================
        history_record = CarHistory(
            car_id=self.car_id,
            battery=int(self.current_battery),
            longitude=self.current_lng,
            latitude=self.current_lat,
            car_status=car.status,
            reported_at=datetime.now(),
            
            # 新增字段
            temperature=round(self.current_temp, 1),
            speed=round(self.current_speed, 1),
            signal=self.current_signal
        )
        db.add(history_record)
        db.commit()

    def _move_and_check_events(self, waypoints, db: Session, task: Task):
        """处理移动逻辑，并检测是否触发里程碑问题"""
        total_points = len(waypoints)
        if total_points < 2: return

        # --- 1. 判断是否到达终点 ---
        if self.current_path_index >= total_points - 1:
            task.status = TASK_COMPLETED
            task.finished_at = datetime.now()
            
            car = db.get(Car, self.car_id)
            if car:
                car.status = CAR_STANDBY
                car.current_task_id = None
            
            # 🔥 任务结束，清空触发记录，以便下次任务重用
            self.triggered_milestones.clear()
            
            # 重置位置状态
            self.current_path_index = 0
            self.segment_progress = 0.0
            self.is_initialized = False
            
            db.commit()
            return
        
        # --- 2. 计算位置插值 (移动) ---
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

        # =========================================
        # 🔥 3. 核心功能：里程碑故障触发
        # =========================================
        # 计算当前进度 (0.0 ~ 1.0)
        current_progress = self.current_path_index / (total_points - 1)

        # 定义触发规则列表：(进度阈值, 标题, 描述)
        milestone_rules = [
            (0.25, "轮胎异常", "左前轮胎压监测数值波动异常，建议检查。"),
            (0.50, "电池高温", "行程过半，电池组核心温度略微升高，请注意散热。"),
            (0.75, "信号干扰", "进入弱信号区域，5G 链路出现丢包现象。")
        ]

        for threshold, name, desc in milestone_rules:
            # 逻辑：如果当前进度 >= 阈值，并且这个阈值还没触发过
            if current_progress >= threshold and threshold not in self.triggered_milestones:
                
                print(f"⚠️ [触发故障] 进度: {int(current_progress*100)}% -> 生成问题: {name}")
                
                # 标记为已触发
                self.triggered_milestones.add(threshold)
                
                # 写入数据库 Problems 表
                new_problem = Problem(
                    task_id=task.id,
                    name=name,
                    description=f"{desc} (触发坐标: {self.current_lat:.4f}, {self.current_lng:.4f})"
                )
                db.add(new_problem)
                db.commit() # 立即提交，让前端能立刻查到

def start_simulation(target_car_id: int):
    print(f"🚀 启动仿真引擎 (ID: {target_car_id})")
    print(f"📋 配置: 速度单位 m/s | 自动报错节点: 25%, 50%, 75%")
    
    driver = VirtualCarDriver(target_car_id)
    
    while True:
        # 每次循环创建一个新的 Session，确保数据最新且不占用连接
        db = SessionLocal()
        try:
            driver.run_step(db)
        except Exception as e:
            print(f"❌ 仿真发生异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            db.close()
        
        time.sleep(SIMULATION_INTERVAL)

if __name__ == "__main__":
    # 修改这里为你数据库中实际存在的 Car ID
    # 且该 Car 必须关联了一个 Task，Task 必须有关联的 Map/Path
    start_simulation(target_car_id=13)