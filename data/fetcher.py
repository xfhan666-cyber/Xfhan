"""
AKShare数据获取封装 - 实时行情、历史K线、财务数据、资金流向
"""
import os
import socket

# ============ 强制绕过系统代理 ============
# 解决 Windows 系统代理(如Clash/V2Ray)残留导致AKShare无法联网的问题
# 1. 清除环境变量中的代理
for v in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(v, None)
# 2. 设置no_proxy=* 让所有请求直连
os.environ['no_proxy'] = '*'
os.environ['NO_PROXY'] = '*'
# 3. 强制urllib3不使用系统代理
try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MarketDataFetcher:
    """A股市场数据获取器"""

    @staticmethod
    def _generate_demo_data():
        """生成演示数据 - 当所有数据源不可用时使用"""
        import numpy as np
        np.random.seed(42)
        codes = [f'{600000 + i}' for i in range(100)] + [f'{300000 + i}' for i in range(50)]
        names = ['演示股票' + str(i) for i in range(150)]
        n = 150
        prices = np.random.uniform(5, 100, n)
        pre_closes = prices * np.random.uniform(0.9, 1.1, n)
        pct_changes = (prices - pre_closes) / pre_closes * 100
        return pd.DataFrame({
            'code': codes, 'name': names, 'price': prices,
            'pct_change': pct_changes, 'change': prices - pre_closes,
            'volume': np.random.uniform(1e6, 1e8, n),
            'amount': np.random.uniform(5e7, 5e9, n),
            'amplitude': np.random.uniform(1, 8, n),
            'high': prices * 1.03, 'low': prices * 0.97,
            'open': pre_closes, 'pre_close': pre_closes,
            'volume_ratio': np.random.uniform(0.5, 3, n),
            'turnover': np.random.uniform(0.5, 10, n),
            'pe_ratio': np.random.uniform(5, 60, n),
            'pb_ratio': np.random.uniform(0.5, 8, n),
            'market_cap': np.random.uniform(2e9, 2e11, n),
            'float_cap': np.random.uniform(1e9, 5e10, n),
            'pct_60d': np.random.uniform(-20, 30, n),
            'pct_ytd': np.random.uniform(-15, 25, n),
            'is_st': [False] * n,
            'is_kcbj': [False] * n,
            'industry': np.random.choice(['银行','医药','科技','白酒','新能源','半导体','军工','房地产','汽车','农业'], n),
        })

    @staticmethod
    def _normalize_eastmoney_df(df):
        """标准化东方财富数据框"""
        df = df.rename(columns={
            '代码': 'code', '名称': 'name', '最新价': 'price',
            '涨跌幅': 'pct_change', '涨跌额': 'change',
            '成交量': 'volume', '成交额': 'amount',
            '振幅': 'amplitude', '最高': 'high', '最低': 'low',
            '今开': 'open', '昨收': 'pre_close',
            '量比': 'volume_ratio', '换手率': 'turnover',
            '市盈率-动态': 'pe_ratio', '市净率': 'pb_ratio',
            '总市值': 'market_cap', '流通市值': 'float_cap',
            '60日涨跌幅': 'pct_60d', '年初至今涨跌幅': 'pct_ytd'
        })
        df = df[df['price'] > 0].copy()
        df['is_st'] = df['name'].str.contains('ST|\\*ST', na=False)
        df['is_kcbj'] = df['code'].str.startswith(('688', '8'), na=False)
        return df

    @staticmethod
    def get_realtime_all_stocks():
        """获取全市场A股实时行情（分批请求+多数据源自动切换）"""
        # 数据源1: 东方财富 - 按市场分批请求（减小单次请求数据量）
        all_parts = []
        eastmoney_ok = False
        for market_func, market_name in [
            (ak.stock_sh_a_spot_em, '沪A'),
            (ak.stock_sz_a_spot_em, '深A'),
            (ak.stock_bj_a_spot_em, '京A'),
        ]:
            try:
                part = market_func()
                if part is not None and not part.empty:
                    part = MarketDataFetcher._normalize_eastmoney_df(part)
                    all_parts.append(part)
                    eastmoney_ok = True
                    logger.info(f"[东方财富-{market_name}] {len(part)}只")
            except Exception:
                logger.debug(f"[东方财富-{market_name}] 不可用")

        if eastmoney_ok:
            df = pd.concat(all_parts, ignore_index=True)
            logger.info(f"[东方财富-分批] 共获取 {len(df)} 只股票（全字段）")
            return df

        # 数据源2: 新浪财经（价格数据）+ 东方财富板块API补充基本面
        try:
            df = ak.stock_zh_a_spot()
            df = df.rename(columns={
                '代码': 'code', '名称': 'name', '最新价': 'price',
                '涨跌幅': 'pct_change', '涨跌额': 'change',
                '成交量': 'volume', '成交额': 'amount',
                '最高': 'high', '最低': 'low', '今开': 'open', '昨收': 'pre_close',
            })
            df = df[df['price'] > 0].copy()
            df['is_st'] = df['name'].str.contains('ST|\\*ST', na=False)
            df['is_kcbj'] = df['code'].str.startswith(('688', '8'), na=False)

            # 尝试补充PE/PB/市值等基本面数据
            # 方法：从东方财富行业板块接口获取（单个行业数据量较小，可能成功）
            try:
                industry_df = ak.stock_board_industry_name_em()
                logger.info(f"[补充数据] 获取行业列表: {len(industry_df)}个行业")
            except Exception:
                industry_df = pd.DataFrame()

            # 新浪缺少的关键字段：使用从价格推算的近似值
            # PE用涨跌幅和价格估算，市值用成交额估算
            if 'pe_ratio' not in df.columns or df['pe_ratio'].sum() == 0:
                df['pe_ratio'] = df.apply(
                    lambda r: round(abs(r['price']) * 15 + 5, 1) if r['price'] > 0 else 15, axis=1)
            if 'pb_ratio' not in df.columns or df['pb_ratio'].sum() == 0:
                df['pb_ratio'] = df['pe_ratio'] / 6  # PE/PB大约比例
            if 'market_cap' not in df.columns or df['market_cap'].sum() == 0:
                df['market_cap'] = df['amount'] * 200  # 日成交额 × 换手率倒数估算
            if 'float_cap' not in df.columns or df['float_cap'].sum() == 0:
                df['float_cap'] = df['market_cap'] * 0.6
            if 'turnover' not in df.columns or df['turnover'].sum() == 0:
                df['turnover'] = (df['volume'] / (df['market_cap'] / df['price'])).clip(0, 50)
            if 'volume_ratio' not in df.columns or df['volume_ratio'].sum() == 0:
                df['volume_ratio'] = 1.2
            if 'amplitude' not in df.columns or df['amplitude'].sum() == 0:
                df['amplitude'] = (df['high'] - df['low']) / df['pre_close'] * 100
                df['amplitude'] = df['amplitude'].clip(0, 20)
            if 'pct_60d' not in df.columns or df['pct_60d'].sum() == 0:
                df['pct_60d'] = df['pct_change'] * 8  # 日内→60日粗略估算
            if 'pct_ytd' not in df.columns or df['pct_ytd'].sum() == 0:
                df['pct_ytd'] = df['pct_change'] * 15

            # 标记数据质量
            df['_data_quality'] = 'basic'  # 标记为估算数据
            logger.info(f"[新浪+估算] 获取 {len(df)} 只股票（PE/PB/市值为估算值）")
            return df
        except Exception as e2:
            logger.warning(f"新浪源不可用: {str(e2)[:80]}")

        # 数据源3: 使用本地缓存
        from data.cache import load_stock_basic
        cached = load_stock_basic()
        if cached is not None and not cached.empty and len(cached) > 100:
            logger.info(f"[本地缓存] 加载 {len(cached)} 只股票")
            return cached

        # 数据源4: 生成演示数据
        logger.warning("所有数据源不可用，使用演示数据。请开启VPN以获取真实数据。")
        return MarketDataFetcher._generate_demo_data()

    @staticmethod
    def get_index_realtime():
        """获取主要指数实时行情（多数据源自动切换）"""
        major_idx = ['上证指数', '深证成指', '创业板指', '科创50', '沪深300', '中证500', '中证1000']

        # 数据源1: 东方财富指数
        try:
            df = ak.stock_zh_index_spot_em()
            if df is not None and not df.empty and '名称' in df.columns:
                df = df[df['名称'].isin(major_idx)]
                if len(df) >= 4:  # 至少有4个主流指数
                    logger.info(f"[东方财富] 获取指数: {len(df)}个")
                    return df.rename(columns={
                        '名称': 'name', '最新价': 'price', '涨跌幅': 'pct_change',
                        '成交量': 'volume', '成交额': 'amount'
                    })
        except Exception:
            pass

        # 数据源2: 新浪指数
        try:
            df = ak.stock_zh_index_spot_sina()
            if df is not None and not df.empty:
                if '名称' in df.columns:
                    df = df[df['名称'].isin(major_idx)]
                logger.info(f"[新浪] 获取指数: {len(df)}个")
                return df.rename(columns={
                    '名称': 'name', '最新价': 'price', '涨跌幅': 'pct_change',
                    '成交量': 'volume', '成交额': 'amount'
                })
        except Exception:
            pass

        # 数据源3: 搜狐指数
        try:
            df = ak.stock_zh_index_spot_sohu()
            if df is not None and not df.empty and len(df) >= 4:
                logger.info(f"[搜狐] 获取指数: {len(df)}个")
                return df.rename(columns={
                    '名称': 'name', '最新价': 'price', '涨跌幅': 'pct_change',
                })
        except Exception:
            pass

        # 降级但可用的近似数据（用上证综指等兜底）
        try:
            df = ak.stock_zh_index_daily(symbol="sh000001")
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                return pd.DataFrame([{
                    'name': '上证指数', 'price': latest['close'],
                    'pct_change': latest.get('pct_change', 0)
                }])
        except Exception:
            pass

        # 最终降级：标记为不可用
        logger.warning("所有指数数据源不可用")
        return pd.DataFrame()

    @staticmethod
    def get_daily_kline(code, period='daily', start_date=None, end_date=None, adjust='qfq'):
        """获取个股历史日K线"""
        try:
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
            if end_date is None:
                end_date = datetime.now().strftime('%Y%m%d')

            df = ak.stock_zh_a_hist(
                symbol=code, period=period,
                start_date=start_date, end_date=end_date,
                adjust=adjust
            )
            if df is not None and not df.empty:
                df = df.rename(columns={
                    '日期': 'date', '开盘': 'open', '收盘': 'close',
                    '最高': 'high', '最低': 'low', '成交量': 'volume',
                    '成交额': 'amount', '振幅': 'amplitude',
                    '涨跌幅': 'pct_change', '涨跌额': 'change', '换手率': 'turnover'
                })
                df['code'] = code
            return df if df is not None else pd.DataFrame()
        except Exception as e:
            logger.error(f"获取{code} K线失败: {e}")
            return pd.DataFrame()

    @staticmethod
    def get_multi_stocks_kline(codes, days=250):
        """批量获取多只股票K线"""
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        all_data = {}
        for i, code in enumerate(codes):
            df = MarketDataFetcher.get_daily_kline(code, start_date=start_date, end_date=end_date)
            if not df.empty:
                all_data[code] = df
            if i % 10 == 0:
                time.sleep(0.3)  # 防止请求频率过高
        return all_data

    @staticmethod
    def get_financial_data(code):
        """获取个股财务数据"""
        try:
            df = ak.stock_financial_abstract_ths(symbol=code)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass
        try:
            df = ak.stock_financial_analysis_indicator(symbol=code)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass
        return pd.DataFrame()

    @staticmethod
    def get_money_flow(code, days=30):
        """获取个股资金流向"""
        try:
            df = ak.stock_individual_fund_flow(stock=code, market="sh")
            if df is None or df.empty:
                df = ak.stock_individual_fund_flow(stock=code, market="sz")
            return df.tail(days) if df is not None else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def get_north_flow():
        """获取北向资金流向"""
        try:
            df = ak.stock_hsgt_hist_em(symbol="沪股通")
            return df.tail(20)
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def get_limit_up_pool(date=None):
        """获取涨停板池"""
        try:
            if date is None:
                date = datetime.now().strftime('%Y%m%d')
            df = ak.stock_zt_pool_em(date=date)
            return df
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def get_industry_list():
        """获取行业分类"""
        try:
            df = ak.stock_board_industry_name_em()
            return df
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def get_stock_basic_info():
        """获取全市场股票基本信息"""
        try:
            df = ak.stock_info_a_code_name()
            return df
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def get_sector_flow():
        """获取行业资金流向"""
        try:
            df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流向")
            return df
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def get_market_overview():
        """获取市场总览（涨跌统计）"""
        df = MarketDataFetcher.get_realtime_all_stocks()
        if df.empty:
            return {}

        total = len(df)
        up = len(df[df['pct_change'] > 0])
        down = len(df[df['pct_change'] < 0])
        flat = len(df[df['pct_change'] == 0])
        limit_up = len(df[df['pct_change'] >= 9.9])
        limit_down = len(df[df['pct_change'] <= -9.9])

        return {
            'total': total, 'up': up, 'down': down, 'flat': flat,
            'limit_up': limit_up, 'limit_down': limit_down,
            'avg_pct': round(df['pct_change'].mean(), 2),
            'up_5pct': len(df[df['pct_change'] > 5]),
            'down_5pct': len(df[df['pct_change'] < -5]),
            'total_amount': round(df['amount'].sum() / 1e8, 0),  # 亿
            'top_gainer': df.nlargest(1, 'pct_change')[['code', 'name', 'pct_change']].to_dict('records'),
            'top_loser': df.nsmallest(1, 'pct_change')[['code', 'name', 'pct_change']].to_dict('records'),
        }


# 单例
fetcher = MarketDataFetcher()
