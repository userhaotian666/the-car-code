import time
import random
from datetime import datetime
# 1. 直接从你的 database.py 导入 SessionLocal
from database import SessionLocal
# 2. 导入模型
from model import Car, CarHistory 

# ================= 状态定义 =================
STATUS_FAULT = 0   # 故障
STATUS_STANDBY = 1 # 待机
STATUS_RUNNING = 2 # 运行中
# ===========================================

def ensure_car_exists(db, car_id):
    """确保 Cars 表里有这辆车"""
    car = db.get(Car, car_id)
    if not car:
        print(f"⚠️ 车辆 {car_id} 不存在，正在创建基础车辆信息...")
        new_car = Car(id=car_id, name=f"仿真测试车_{car_id}", status=0)
        db.add(new_car)
        db.commit()
        print(f"✅ 车辆 {car_id} 创建成功！")
    return car_id

def simulate_movement(car_id: int):
    db = SessionLocal()
    
    try:
        ensure_car_exists(db, car_id)
        
        print(f"🚀 开始模拟车辆 {car_id} 的运行数据...")
        print("   (包含状态模拟: 0=故障, 1=待机, 2=运行)")
        print("按 Ctrl+C 停止脚本")

        # 初始位置 (上海人民广场附近)
        current_lat = 31.2304
        current_lng = 121.4737
        current_battery = 100
        
        # 初始状态配置
        current_status = STATUS_RUNNING # 默认先跑起来
        state_timer = 0 # 状态持续倒计时
        
        while True:
            # --- A. 状态切换逻辑 (状态机) ---
            # 如果倒计时结束，随机切换到一个新状态
            if state_timer <= 0:
                rand_val = random.random()
                if rand_val < 0.05: 
                    # 5% 概率发生故障
                    current_status = STATUS_FAULT
                    state_timer = random.randint(5, 10) # 故障持续 5-10秒
                    print("⚠️ 突发故障！车辆停止...")
                elif rand_val < 0.20:
                    # 15% 概率进入待机
                    current_status = STATUS_STANDBY
                    state_timer = random.randint(3, 8)  # 待机持续 3-8秒
                    print("⏸️ 车辆待机中...")
                else:
                    # 80% 概率正常运行
                    current_status = STATUS_RUNNING
                    state_timer = random.randint(10, 30) # 运行持续 10-30秒
                    print("▶️ 车辆恢复运行...")
            
            # 倒计时递减
            state_timer -= 1

            # --- B. 根据状态决定行为 ---
            if current_status == STATUS_RUNNING:
                # 只有运行状态下，车才会动
                delta_lat = random.uniform(-0.002, 0.002) 
                delta_lng = random.uniform(-0.002, 0.002)
                current_lat += delta_lat
                current_lng += delta_lng
                
                # 运行时耗电
                if random.random() < 0.2: # 20%概率掉电
                    current_battery -= 1
            
            elif current_status == STATUS_STANDBY:
                # 待机状态：位置不变
                # 耗电极慢 (5%概率掉电)
                if random.random() < 0.05:
                    current_battery -= 1
            
            elif current_status == STATUS_FAULT:
                # 故障状态：位置不变，电量不变(或者你可以模拟漏电)
                pass

            # 电池保护
            if current_battery <= 0:
                current_battery = 100
                print("🔋 [系统消息] 电池耗尽，已自动更换电池")

            # --- C. 插入数据库 ---
            history_record = CarHistory(
                car_id=car_id,
                battery=current_battery,
                longitude=current_lng, 
                latitude=current_lat,
                # 【关键】这里写入当前动态变化的状态
                car_status=current_status,
                reported_at=datetime.now()
            )
            
            db.add(history_record)
            db.commit()
            
            # 打印日志方便观察
            status_str = {0: "❌故障", 1: "⏸️待机", 2: "🚀运行"}.get(current_status)
            print(f"Update: [{status_str}] 电量:{current_battery}% 坐标:({current_lat:.4f}, {current_lng:.4f})")

            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 模拟已停止")
    except Exception as e:
        print(f"❌ 发生错误: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    simulate_movement(car_id=3)