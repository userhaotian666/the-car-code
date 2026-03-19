import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

# 导入你的配置
from database import AsyncSessionLocal
from model import Task, TaskStatus, Car # 假设你定义了 CarStatus

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scheduler")
logging.getLogger("apscheduler").setLevel(logging.WARNING)
CAR_FAULT = 0
CAR_STANDBY = 1
CAR_RUNNING = 2
scheduler = AsyncIOScheduler()

async def check_and_start_due_tasks():
    """
    核心函数：扫描所有 [已定时] 且 [时间已到] 且 [状态为SCHEDULED] 的任务
    """
    logger.debug("正在扫描到期任务...") # debug级别，避免刷屏
    
    async with AsyncSessionLocal() as db:
        now = datetime.now()
        current_time = now.time()
        today=now.date()
        # 1. 查询条件：
        # - 是定时任务 (is_scheduled = True)
        # - 状态是等待中 (status = SCHEDULED)
        # - 设定时间 <= 当前时间 (scheduled_start <= now)
        stmt = select(Task).options(selectinload(Task.executor)).where(
            and_(
                Task.is_scheduled == True,
                Task.scheduled_start <= current_time,
                Task.scheduled_end >= current_time,
                or_(
                    Task.status == TaskStatus.SCHEDULED,
                    Task.status == TaskStatus.COMPLETED,
                )
            )
        )
        
        result = await db.execute(stmt)
        due_tasks = result.scalars().all()
        
        if not due_tasks:
            return # 没有到期任务，直接结束

        # 2. 批量处理启动逻辑
        for task in due_tasks:
            logger.info(f"⏰ 任务 {task.id} [{task.name}] 时间已到 ({task.scheduled_start})，准备启动...")
            
            # 这里的逻辑和你的 /start 接口逻辑保持一致
            
            # A. 检查车辆
            if not task.executor:
                logger.warning(f"⚠️ 任务 {task.id} 到期但未绑定车辆，跳过启动")
                # 可以在这里加逻辑：如果没车，是否要把状态改为 PENDING 让调度器去分配？
                # task.status = TaskStatus.PENDING 
                continue
            
            if task.executor.status == 0: # 假设 0 是故障
                 logger.error(f"❌ 任务 {task.id} 车辆故障，无法启动")
                 # task.status = TaskStatus.FAILED # 可选：标记失败
                 continue

            if task.executor.status == 2 and task.executor.current_task_id != task.id:
                 logger.warning(f"⚠️ 任务 {task.id} 车辆正在忙其他任务，稍后重试")
                 continue

            # B. 正式启动
            task.status = TaskStatus.RUNNING
            task.executor.status = 2 # CAR_RUNNING
            
            # 可选：记录实际开始时间
            # task.actual_start_at = datetime.now()
            
            logger.info(f"✅ 任务 {task.id} 已自动启动，车辆 {task.executor.name} 出发！")
        
        # 3. 提交更改
        await db.commit()

async def start_scheduler():
    """启动调度器"""
    # 添加一个【间隔任务】：每 5 秒运行一次 check_and_start_due_tasks
    # 即使服务器重启，只要数据库里的时间没变，下次启动也能马上扫到这些任务，不会丢失
    scheduler.add_job(
        check_and_start_due_tasks, 
        'interval', 
        seconds=5,  # 扫描频率，根据业务实时性要求调整
        id="task_scanner",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("🚀 定时任务监控服务已启动 (Polling Mode)")