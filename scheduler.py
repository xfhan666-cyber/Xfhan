"""
定时任务调度器 - 盘中定时扫描，自动生成和推送信号
"""
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import logging
from signals.generator import generator
from signals.notifier import notifier
from config import SCAN_HOURS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
last_scan_time = None


def scan_and_notify():
    """扫描市场生成信号并推送"""
    global last_scan_time
    now = datetime.now()
    logger.info(f"[{now.strftime('%H:%M:%S')}] 定时扫描开始...")

    try:
        # 只在交易时间执行
        if now.weekday() >= 5:
            logger.info("非交易日，跳过")
            return

        # 运行所有策略
        signals = generator.run_all_strategies()
        top_picks = generator.get_top_picks(10)

        if top_picks:
            # 发送Top5信号到手机
            notifier.send_batch_signals(top_picks, max_send=5)
            logger.info(f"已推送 {min(5, len(top_picks))} 条信号")
        else:
            logger.info("当前无符合条件的交易信号")

        last_scan_time = now
    except Exception as e:
        logger.error(f"扫描失败: {e}")


def close_market_report():
    """收盘后生成当日汇总"""
    try:
        signals = generator.all_signals
        if not signals:
            signals = generator.run_all_strategies()

        report = generator.get_signals_summary()
        notifier.send_daily_report(report)
        logger.info("收盘报告已发送")
    except Exception as e:
        logger.error(f"收盘报告失败: {e}")


def start_scheduler():
    """启动定时任务"""
    # 盘中每小时扫描（9:30-15:00）
    for hour in SCAN_HOURS:
        scheduler.add_job(
            scan_and_notify,
            'cron',
            day_of_week='mon-fri',
            hour=hour,
            minute=30,
            id=f'scan_{hour}',
            replace_existing=True
        )

    # 收盘后16:30生成报告
    scheduler.add_job(
        close_market_report,
        'cron',
        day_of_week='mon-fri',
        hour=16,
        minute=30,
        id='close_report',
        replace_existing=True
    )

    scheduler.start()
    logger.info("📅 定时任务调度器已启动")
    logger.info(f"   盘中扫描: {SCAN_HOURS}点")
    logger.info(f"   收盘报告: 16:30")


def stop_scheduler():
    """停止调度器"""
    scheduler.shutdown()
    logger.info("调度器已停止")


def get_scheduler_status() -> dict:
    """获取调度器状态"""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            'id': job.id,
            'next_run': job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else 'N/A',
        })
    return {
        'running': scheduler.running,
        'last_scan': last_scan_time.strftime('%Y-%m-%d %H:%M:%S') if last_scan_time else '未执行',
        'jobs': jobs
    }
