import asyncio
import random
import logging
from datetime import datetime
from sqlalchemy import select, desc, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

# ================= 📦 项目依赖 =================
# 确保 database.py 中导出了 AsyncSessionLocal
from database import AsyncSessionLocal
# 确保 model.py 中导出了以下模型和枚举
from model import Task, Car, CarHistory, TaskStatus

# ================= ⚙️ 仿真参数配置 =================
SYSTEM_MODE = "SIMULATION"   # 模式: REAL / SIMULATION
SIMULATION_INTERVAL = 2.0    # 仿真步长(秒)
SCHEDULER_INTERVAL = 3.0     # 调度扫描间隔(秒)

# 物理参数
MOVE_SPEED_RATIO = 0.1       # 移动插值步长 (0.1代表两点间走10步)
BATTERY_CONSUMPTION_RUNNING = 0.1  # 行驶耗电量/次
BATTERY_CONSUMPTION_IDLE = 0.01    # 待机耗电量/次
AMBIENT_TEMP = 25.0          # 环境温度

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger("simulator")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

class VirtualCarDriver:
    def __init__(self, car_id: int, task_id: int):
        self.car_id = car_id
        self.task_id = task_id
        self.running = True
        
        # 导航状态
        self.current_path_index = 0
        self.segment_progress = 0.0
        self.is_initialized = False
        self.moving_forward = True
        
        # ==================================================
        # ✨ 强类型初始化 (防止 NULL 插入数据库)
        # ==================================================
        self.current_lat = 0.0
        self.current_lng = 0.0
        self.current_battery = 100.0  # 默认满电
        self.current_speed = 0.0
        self.current_temp = AMBIENT_TEMP
        self.current_signal = 100

    async def run_loop(self):
        """仿真主循环"""
        logger.info(f"🚗 [Car-{self.car_id}] 启动仿真进程 (Task-{self.task_id})")
        while self.running:
            try:
                async with AsyncSessionLocal() as db:
                    should_continue = await self._step(db)
                    if not should_continue:
                        self.running = False
            except Exception as e:
                logger.error(f"❌ [Car-{self.car_id}] 仿真发生未知异常: {e}", exc_info=True)
                await asyncio.sleep(5) 
            
            if self.running:
                await asyncio.sleep(SIMULATION_INTERVAL)
        logger.info(f"🛑 [Car-{self.car_id}] 仿真进程结束")

    async def _step(self, db: AsyncSession) -> bool:
        """单步执行逻辑"""
        # 1. 查询任务及其关联信息
        stmt = (
            select(Task)
            .options(selectinload(Task.executor), selectinload(Task.path_info))
            .where(Task.id == self.task_id)
        )
        result = await db.execute(stmt)
        task = result.scalars().first()

        if not task: 
            logger.warning(f"⚠️ Task-{self.task_id} 未找到，退出。")
            return False

        # 2. 状态校验 (兼容 int 和 Enum)
        current_status_val = task.status.value if hasattr(task.status, 'value') else task.status
        running_val = TaskStatus.RUNNING.value if hasattr(TaskStatus.RUNNING, 'value') else 2
        paused_val = TaskStatus.PAUSED.value if hasattr(TaskStatus.PAUSED, 'value') else 6
        
        # 只有 RUNNING 和 PAUSED 状态下才继续仿真循环，其他状态(完成/失败/取消)退出
        if current_status_val not in [running_val, paused_val]:
            logger.info(f"ℹ️ Task-{self.task_id} 状态变为 {task.status}，仿真结束。")
            return False

        car = task.executor 
        if not car: 
            logger.error(f"❌ Task-{self.task_id} 丢失 executor 车辆信息。")
            return False

        # =====================================================
        # 3. 初始化位置 (处理新任务 vs 断点续传)
        # =====================================================
        if not self.is_initialized:
            # 检查是否有路径
            has_path = task.path_info and task.path_info.waypoints and len(task.path_info.waypoints) > 0
            
            if has_path:
                waypoints = task.path_info.waypoints
                start_point = waypoints[0]

                # A. 查最新的历史记录
                history_stmt = (
                    select(CarHistory)
                    .where(CarHistory.car_id == self.car_id)
                    .order_by(desc(CarHistory.reported_at))
                    .limit(1)
                )
                h_result = await db.execute(history_stmt)
                last_history = h_result.scalars().first()

                # B. 判断历史记录是否属于“当前任务”
                is_resume = False
                if last_history and task.created_at:
                    # 如果历史记录时间 晚于 任务创建时间 -> 续传
                    if last_history.reported_at > task.created_at:
                        is_resume = True
                
                if is_resume and last_history:
                    # --- 续传模式 ---
                    # ✨ 强制 float 转换，防止 None 或 Decimal 问题
                    hist_lat = float(last_history.latitude) if last_history.latitude is not None else 0.0
                    hist_lng = float(last_history.longitude) if last_history.longitude is not None else 0.0
                    
                    logger.info(f"🔄 [Car-{self.car_id}] 任务恢复中，坐标: ({hist_lat:.5f}, {hist_lng:.5f})")
                    
                    self.current_battery = float(last_history.battery) if last_history.battery is not None else 100.0
                    self._recover_execution_state(waypoints, hist_lat, hist_lng)
                else:
                    # --- 新任务模式 ---
                    logger.info(f"🆕 [Car-{self.car_id}] 新任务启动，重置到起点")
                    # ✨ 确保取到的 waypoint 数据有效
                    self.current_lat = float(start_point.get("lat", 0.0))
                    self.current_lng = float(start_point.get("lng", 0.0))
                    self.current_path_index = 0
                    self.segment_progress = 0.0
                    self.moving_forward = True
            else:
                logger.warning(f"⚠️ Task-{self.task_id} 没有路径信息，使用默认坐标(0,0)")
                self.current_lat = 0.0
                self.current_lng = 0.0
            
            self.is_initialized = True

        # 4. 判断逻辑：是否暂停
        is_paused = (current_status_val == paused_val)

        # 5. 物理环境计算 (温度、信号)
        self.current_temp = 25.0 + random.uniform(0, 5)
        self.current_signal = max(0, min(100, int(random.gauss(85, 10))))

        if is_paused:
            # === ⏸️ 暂停逻辑 ===
            self.current_speed = 0.0
            # 待机耗电
            self.current_battery = max(0, self.current_battery - BATTERY_CONSUMPTION_IDLE)
            # 坐标保持不变 (self.current_lat/lng 不更新)
        else:
            # === ▶️ 运行逻辑 ===
            self.current_battery = max(0, self.current_battery - BATTERY_CONSUMPTION_RUNNING)
            target_speed = random.uniform(5.0, 15.0)
            self.current_speed = (self.current_speed * 0.8) + (target_speed * 0.2)
            
            # 仅在有电且有路径时移动
            if self.current_battery > 0 and task.path_info and task.path_info.waypoints:
                await self._move_smoothly(task.path_info.waypoints, db, task, car)

        # 6. 持续写入 History (确保字段不为 None)
        # 强制 int/float 转换，作为写入数据库前的最后一道防线
        safe_battery = int(self.current_battery)
        safe_lat = float(self.current_lat)
        safe_lng = float(self.current_lng)
        safe_speed = float(self.current_speed)
        
        history = CarHistory(
            car_id=car.id,
            battery=safe_battery,
            longitude=safe_lng,
            latitude=safe_lat,
            car_status=current_status_val, # 使用当前的任务状态数值
            reported_at=datetime.now(),
            speed=round(safe_speed, 1),
            temperature=round(self.current_temp, 1),
            signal=self.current_signal
        )
        db.add(history)
        await db.commit()
        return True

    def _recover_execution_state(self, waypoints, car_lat, car_lng):
        """寻找最近的路径点，用于断点续传"""
        min_dist = float('inf')
        closest_index = 0
        
        for i, wp in enumerate(waypoints):
            wp_lat = float(wp.get("lat", 0.0))
            wp_lng = float(wp.get("lng", 0.0))
            dist = (wp_lat - car_lat) ** 2 + (wp_lng - car_lng) ** 2
            if dist < min_dist:
                min_dist = dist
                closest_index = i
        
        self.current_path_index = closest_index
        self.current_lat = car_lat
        self.current_lng = car_lng
        self.segment_progress = 0.0 
        
        # 简单方向推断
        if closest_index >= len(waypoints) - 1:
             self.moving_forward = False
        else:
             self.moving_forward = True

    async def _move_smoothly(self, waypoints, db: AsyncSession, task: Task, car: Car):
        """处理平滑移动与到达判断"""
        total_points = len(waypoints)
        if total_points < 2: return
        
        target_index = self.current_path_index + 1 if self.moving_forward else self.current_path_index - 1
        
        # --- 到达终点处理 ---
        if target_index >= total_points:
            should_continue = task.is_scheduled and (task.scheduled_end is None or datetime.now().time() < task.scheduled_end)
            if should_continue:
                self.moving_forward = False
                self.segment_progress = 0.0
                return 
            else:
                await self._complete_task(db, task, car, "到达目的地")
                return

        # --- 到达起点处理 ---
        if target_index < 0:
            should_continue = task.is_scheduled and (task.scheduled_end is None or datetime.now().time() < task.scheduled_end)
            if should_continue:
                self.moving_forward = True
                self.segment_progress = 0.0
                return
            else:
                await self._complete_task(db, task, car, "定时任务结束")
                return

        # --- 插值移动计算 ---
        p_from = waypoints[self.current_path_index]
        p_to   = waypoints[target_index]
        self.segment_progress += MOVE_SPEED_RATIO

        lat_f = float(p_from.get("lat", 0.0))
        lng_f = float(p_from.get("lng", 0.0))
        lat_t = float(p_to.get("lat", 0.0))
        lng_t = float(p_to.get("lng", 0.0))

        if self.segment_progress >= 1.0:
            self.segment_progress = 0.0
            self.current_path_index = target_index 
            self.current_lat = lat_t
            self.current_lng = lng_t
        else:
            self.current_lat = lat_f + (lat_t - lat_f) * self.segment_progress
            self.current_lng = lng_f + (lng_t - lng_f) * self.segment_progress

    async def _complete_task(self, db: AsyncSession, task: Task, car: Car, reason: str):
        """任务完成后的收尾：更新状态并插入停止记录"""
        logger.info(f"🏁 Task-{task.id} 完成: {reason}")
        
        # 1. 更新任务状态
        task.status = TaskStatus.COMPLETED
        task.finished_at = datetime.now()
        
        # 2. 如果 Car 表有 status 字段，可在此释放
        if hasattr(car, "status"):
             car.status = 1  # STANDBY
        
        # 3. 速度归零
        self.current_speed = 0.0
        
        # 4. 插入最后一条记录 (确保速度为0，位置定格)
        final_history = CarHistory(
            car_id=car.id,
            battery=int(self.current_battery),
            longitude=float(self.current_lat), # 保证 Float
            latitude=float(self.current_lng),  # 保证 Float
            car_status=1,                      # 这里的状态码看你定义，假设 1=Standby
            reported_at=datetime.now(),
            speed=0.0,                         # 明确为 0
            temperature=round(self.current_temp, 1),
            signal=self.current_signal
        )
        db.add(final_history)
        await db.commit()

class SimulationScheduler:
    """调度器：负责监听数据库并管理协程"""
    def __init__(self):
        self.active_simulators = {}

    async def start(self):
        logger.info(f"🕹️ 仿真调度器启动 | 模式: {SYSTEM_MODE}")
        if SYSTEM_MODE != "SIMULATION":
            while True: await asyncio.sleep(3600)
        
        while True:
            try:
                async with AsyncSessionLocal() as db:
                    await self._scan_and_schedule(db)
            except Exception as e:
                logger.error(f"调度器扫描异常: {e}")
            await asyncio.sleep(SCHEDULER_INTERVAL)

    async def _scan_and_schedule(self, db: AsyncSession):
        # 扫描 RUNNING 和 PAUSED 状态的任务
        stmt = (
            select(Task)
            .options(selectinload(Task.executor))
            .where(
                or_(
                    Task.status == TaskStatus.RUNNING,
                    Task.status == TaskStatus.PAUSED
                )
            )
        )
        result = await db.execute(stmt)
        active_tasks = result.scalars().all()

        for task in active_tasks:
            # 如果该任务不在内存中运行，且有绑定的车辆，则启动
            if task.id not in self.active_simulators and task.executor:
                status_str = "运行中" if task.status == TaskStatus.RUNNING else "暂停中"
                logger.info(f"⚡ 启动仿真 ({status_str}): Task-{task.id} -> Car-{task.executor.id}")
                
                driver = VirtualCarDriver(task.executor.id, task.id)
                t = asyncio.create_task(driver.run_loop())
                
                # 任务结束后的回调清理
                t.add_done_callback(lambda _, tid=task.id: self.active_simulators.pop(tid, None))
                self.active_simulators[task.id] = t

if __name__ == "__main__":
    try:
        scheduler = SimulationScheduler()
        asyncio.run(scheduler.start())
    except KeyboardInterrupt:
        logger.info("🛑 用户手动停止仿真")