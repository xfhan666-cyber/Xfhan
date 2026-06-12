"""
全局配置文件
"""
import os

# 项目路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CACHE_DB = os.path.join(DATA_DIR, 'market_cache.db')

# ========== 数据源配置 ==========
# AKShare 无需Token，直接使用
# Tushare Token（可选，用于更完整的财务数据）
TUSHARE_TOKEN = os.environ.get('TUSHARE_TOKEN', '')

# ========== 消息推送配置 ==========
# 企业微信机器人（推荐主力通道）
WECOM_CORP_ID = os.environ.get('WECOM_CORP_ID', '')
WECOM_CORP_SECRET = os.environ.get('WECOM_CORP_SECRET', '')
WECOM_AGENT_ID = os.environ.get('WECOM_AGENT_ID', '')

# PushPlus（备用通道，免费200条/天）
PUSHPLUS_TOKEN = os.environ.get('PUSHPLUS_TOKEN', '')

# Server酱（快速测试，免费5条/天）- key存储在.env文件中，不上传到GitHub
SERVERCHAN_KEY = os.environ.get('SERVERCHAN_KEY', '')

# ========== 策略默认参数 ==========
DEFAULT_STRATEGY_PARAMS = {
    'multi_factor': {
        'top_n': 30,
        'rebalance_freq': 'monthly',
        'weights': {'pe': 0.25, 'pb': 0.15, 'roe': 0.20, 'growth': 0.15, 'momentum': 0.10, 'turnover': 0.10, 'volatility': 0.05}
    },
    'pb_roe': {
        'top_n': 20,
        'pb_threshold': 0.8,
        'roe_min': 15,
        'roe_std_max': 5,
        'min_volume': 50000000
    },
    'trend_momentum': {
        'ma_short': 20,
        'ma_mid': 60,
        'ma_long': 120,
        'volume_ratio': 1.5,
        'capital_inflow_min': 50000000,
        'stop_loss_pct': 8
    },
    'mean_reversion': {
        'decline_pct': 10,
        'turnover_max': 1,
        'stop_profit_pct': 5,
        'stop_loss_pct': 3,
        'max_hold_days': 10
    },
    'smallcap_growth': {
        'top_n': 15,
        'revenue_growth_min': 20,
        'market_cap_max': 20000000000,
        'turnover_min': 2,
        'turnover_max': 8
    },
    'limit_up': {
        'seal_time_min': 60,
        'seal_fund_ratio': 0.01,
        'max_open_pct': 5
    },
    'first_board': {
        'seal_deadline': '10:30',
        'min_sector_stocks': 3,
        'float_cap_min': 30e8,
        'float_cap_max': 80e8,
        'seal_amount_ratio': 0.20,
        'volume_ratio_min': 3.0,
        'recent_limit_up_count': 2,
        'recent_days': 120,
        'single_stop_loss': -3.0,
        'daily_stop_loss': -2.0,
        'monthly_stop_loss': -10.0,
        'top_n': 10,
    }
}

# ========== 风险控制参数 ==========
RISK_CONTROL = {
    'max_single_position': 0.15,    # 单票最大仓位
    'max_industry_exposure': 0.30,  # 单行业最大暴露
    'portfolio_stop_loss': 0.12,    # 组合层面止损
    'max_daily_trades': 5,         # 单日最大交易次数
}

# ========== 调度配置 ==========
# 盘中扫描时间点（24小时制）
SCAN_HOURS = [9, 10, 11, 13, 14, 15]
# 收盘后复盘时间
CLOSE_SCAN_HOUR = 16
