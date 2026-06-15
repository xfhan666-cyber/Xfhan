"""
真实回测引擎 - 使用AKShare历史数据，非随机模拟
对比原始 engine.py 的 generate_sample_backtest（随机数造假），本模块完全基于真实K线
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RealBacktestEngine:
    """
    真实回测引擎

    支持的回测模式：
    1. 单策略回测 - 指定策略+股票池+时间段
    2. 策略横向对比 - 同一时间段对比多个策略
    3. 信号模拟回测 - 基于历史信号模拟交易

    限制说明（诚实披露）：
    - 技术面策略（趋势动量、超跌反弹）→ 可完整回测 ✅
    - 基本面策略（多因子、PB-ROE）→ 仅能用估算值回测 ⚠️
    - 打板策略（首板、涨停板）→ 需要逐笔数据，仅能做涨停统计回测 ⚠️
    """

    def __init__(self):
        self.benchmark_code = '000300'  # 默认沪深300基准

    # ============================================================
    # 数据获取
    # ============================================================

    def _get_stock_pool(self, source: str = 'hs300', size: int = 50) -> List[str]:
        """
        获取回测股票池
        source: 'hs300' | 'zz500' | 'top_volume' | 'random_sample'
        """
        try:
            import akshare as ak

            if source == 'hs300':
                df = ak.index_stock_cons(symbol="000300")
                codes = df['品种代码'].tolist() if '品种代码' in df.columns else df['stock_code'].tolist()
            elif source == 'zz500':
                df = ak.index_stock_cons(symbol="000905")
                codes = df['品种代码'].tolist() if '品种代码' in df.columns else df['stock_code'].tolist()
            elif source == 'all_a':
                # 全A股（取活跃的）
                df = ak.stock_zh_a_spot()
                if df is not None and not df.empty:
                    df = df[df['代码'].str.match(r'^(60[0-3]|000|002)')]  # 主板
                    df = df.nlargest(size * 2, '成交额')
                    codes = df['代码'].tolist()
                else:
                    codes = []
            else:
                codes = []

            # 过滤掉北交所、ST
            codes = [c for c in codes if not c.startswith(('8', '4'))]
            return codes[:size]

        except Exception as e:
            logger.warning(f"获取股票池失败: {e}，使用默认池")
            # 默认50只代表性股票
            return [
                '600519', '000858', '601398', '600036', '601318',  # 茅台、五粮液、工行、招行、平安
                '000333', '600276', '600887', '601012', '002415',  # 美的、恒瑞、伊利、隆基、海康
                '600900', '600585', '600048', '000002', '601668',  # 长江电力、海螺、保利、万科、建筑
                '600030', '000651', '002594', '600104', '601888',  # 中信、格力、比亚迪、上汽、中免
                '300750', '300059', '300015', '688981', '603259',  # 宁德、东财、爱尔、中芯、药明
                '002714', '000568', '601899', '600809', '000725',  # 牧原、泸州、紫金、汾酒、京东方
                '601857', '600031', '601088', '600690', '000063',  # 中石油、三一、神华、海尔、中兴
                '002475', '300124', '600436', '002230', '603501',  # 立讯、汇川、片仔癀、讯飞、韦尔
                '601225', '600019', '601939', '601288', '600028',  # 陕煤、宝钢、建行、农行、中石化
                '000001', '002142', '601166', '600000', '600016',  # 平安银行、宁波、兴业、浦发、民生
            ]

    def _get_historical_data(self, codes: List[str], start_date: str,
                             end_date: str) -> Dict[str, pd.DataFrame]:
        """
        批量获取历史日K线数据
        返回: {code: DataFrame with OHLCV}
        """
        import akshare as ak

        all_data = {}
        total = len(codes)
        failed = 0

        for i, code in enumerate(codes):
            try:
                df = ak.stock_zh_a_hist(
                    symbol=code, period='daily',
                    start_date=start_date, end_date=end_date,
                    adjust='qfq'  # 前复权
                )
                if df is not None and not df.empty and len(df) >= 60:
                    df = df.rename(columns={
                        '日期': 'date', '开盘': 'open', '收盘': 'close',
                        '最高': 'high', '最低': 'low', '成交量': 'volume',
                        '成交额': 'amount', '振幅': 'amplitude',
                        '涨跌幅': 'pct_change', '换手率': 'turnover'
                    })
                    df['date'] = pd.to_datetime(df['date'])
                    df = df.sort_values('date').reset_index(drop=True)
                    all_data[code] = df
                else:
                    failed += 1

                if (i + 1) % 10 == 0:
                    progress = (i + 1) / total * 100
                    logger.info(f"  数据获取: {i+1}/{total} ({progress:.0f}%) | 失败{failed}只")

                time.sleep(0.15)  # 控制请求频率

            except Exception as e:
                failed += 1
                if failed <= 3:  # 只打印前3个错误
                    logger.debug(f"  {code} 获取失败: {str(e)[:50]}")

        logger.info(f"  数据获取完成: {len(all_data)}/{total} 成功, {failed} 失败")
        return all_data

    def _get_benchmark_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """获取基准指数数据"""
        import akshare as ak
        try:
            df = ak.stock_zh_index_daily(symbol=f"sh{self.benchmark_code}")
            if df is not None and not df.empty:
                df = df.rename(columns={'date': 'date', 'close': 'close'})
                df['date'] = pd.to_datetime(df['date'])
                df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
                df = df.sort_values('date').reset_index(drop=True)
                df['return'] = df['close'].pct_change()
                return df
        except Exception as e:
            logger.warning(f"基准数据获取失败: {e}")

        # Fallback: 用指数日线接口
        try:
            df = ak.index_zh_a_hist(symbol=self.benchmark_code, period='daily',
                                     start_date=start_date, end_date=end_date)
            if df is not None and not df.empty:
                df = df.rename(columns={'日期': 'date', '收盘': 'close'})
                df['date'] = pd.to_datetime(df['date'])
                df['return'] = df['close'].pct_change()
                return df
        except Exception:
            pass
        return pd.DataFrame()

    # ============================================================
    # 策略回测
    # ============================================================

    def backtest_trend_momentum(self, hist_data: Dict[str, pd.DataFrame],
                                 start_date: str, end_date: str,
                                 ma_short: int = 20, ma_long: int = 60,
                                 top_n: int = 10) -> Dict:
        """
        趋势动量策略回测（基于真实K线）
        逻辑：MA短>MA长 → 买入；反之卖出
        """
        trades = []
        daily_values = [1.0]
        dates = pd.date_range(start=start_date, end=end_date, freq='B')

        # 为每只股票计算信号
        all_signals = {}
        for code, df in hist_data.items():
            if len(df) < ma_long + 5:
                continue
            df = df.copy()
            df['ma_s'] = df['close'].rolling(ma_short).mean()
            df['ma_l'] = df['close'].rolling(ma_long).mean()
            df['signal'] = (df['ma_s'] > df['ma_l']).astype(int)
            df['position'] = df['signal'].diff()
            all_signals[code] = df

        # 逐月调仓模拟
        for i, date in enumerate(dates[ma_long:], ma_long):
            if i >= len(dates):
                break

            # 选出当前有买入信号的股票
            candidates = []
            for code, df in all_signals.items():
                row = df[df['date'] <= dates[i]]
                if row.empty:
                    continue
                latest = row.iloc[-1]
                if latest.get('signal', 0) == 1:
                    # 计算近期动量（过去20日涨幅）
                    if len(row) >= 21:
                        momentum = (row['close'].iloc[-1] / row['close'].iloc[-21] - 1) * 100
                    else:
                        momentum = 0
                    candidates.append((code, momentum, latest['close']))

            # 选top_n只动量最强的
            candidates.sort(key=lambda x: x[1], reverse=True)
            selected = candidates[:top_n]

            # 等权买入
            if selected:
                weight = 1.0 / len(selected)
                day_return = 0
                for code, _, price in selected:
                    # 找出该股票的明日收益
                    df = all_signals[code]
                    next_rows = df[df['date'] > dates[i]]
                    if not next_rows.empty:
                        next_close = next_rows.iloc[0]['close']
                        ret = (next_close / price - 1) * weight
                        day_return += ret
                        trades.append({
                            'code': code, 'entry_date': dates[i],
                            'entry_price': price, 'exit_price': next_close,
                            'return_pct': round(ret / weight * 100, 2)
                        })

                daily_values.append(daily_values[-1] * (1 + day_return / 100))
            else:
                daily_values.append(daily_values[-1])

        return self._calc_metrics(daily_values, trades, '趋势动量策略')

    def backtest_mean_reversion(self, hist_data: Dict[str, pd.DataFrame],
                                 start_date: str, end_date: str,
                                 decline_pct: float = 10,
                                 hold_days: int = 5) -> Dict:
        """
        超跌反弹策略回测
        逻辑：过去N日跌幅超阈值 → 买入，持有M天 → 卖出
        """
        trades = []
        daily_values = [1.0]
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        lookback = 20
        min_data = lookback + hold_days + 5

        for code, df in hist_data.items():
            if len(df) < min_data:
                continue
            df = df.copy()
            df['ret_20d'] = df['close'].pct_change(lookback) * 100

            for i in range(lookback, len(df) - hold_days):
                if df['ret_20d'].iloc[i] <= -decline_pct:
                    entry = df['close'].iloc[i]
                    exit_price = df['close'].iloc[i + hold_days]
                    ret = (exit_price / entry - 1) * 100
                    trades.append({
                        'code': code,
                        'entry_date': df['date'].iloc[i],
                        'exit_date': df['date'].iloc[i + hold_days],
                        'entry_price': round(entry, 2),
                        'exit_price': round(exit_price, 2),
                        'return_pct': round(ret, 2)
                    })

        if trades:
            # 构建组合净值
            trades_df = pd.DataFrame(trades)
            # 按月聚合所有交易
            trades_df['entry_month'] = pd.to_datetime(trades_df['entry_date']).dt.to_period('M')
            monthly_returns = trades_df.groupby('entry_month')['return_pct'].mean()
            cumulative = 1.0
            values = [1.0]
            for r in monthly_returns:
                cumulative *= (1 + r / 100)
                values.append(cumulative)
            daily_values = values

        return self._calc_metrics(daily_values, trades, '超跌反弹策略')

    def backtest_ma_crossover_system(self, hist_data: Dict[str, pd.DataFrame],
                                      start_date: str, end_date: str,
                                      params: Dict = None) -> Dict:
        """
        通用均线交叉系统回测 - 可配置参数的版本
        用于测试不同参数组合
        """
        p = params or {'ma_short': 20, 'ma_long': 60, 'top_n': 10}
        return self.backtest_trend_momentum(
            hist_data, start_date, end_date,
            ma_short=p['ma_short'], ma_long=p['ma_long'],
            top_n=p['top_n']
        )

    # ============================================================
    # 综合回测入口
    # ============================================================

    def run_full_backtest(self, strategy_type: str = 'trend',
                          lookback_days: int = 365,
                          stock_pool: str = 'top_volume',
                          pool_size: int = 50) -> Dict:
        """
        完整回测流程

        Args:
            strategy_type: 'trend' | 'reversion' | 'both'
            lookback_days: 回测天数
            stock_pool: 股票池来源
            pool_size: 股票池大小

        Returns:
            dict with metrics, trades, benchmark comparison
        """
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y%m%d')

        logger.info(f"🔄 真实回测开始: {start_date} ~ {end_date}")
        logger.info(f"   策略: {strategy_type} | 股票池: {stock_pool} | 数量: {pool_size}")

        # 1. 获取股票池
        logger.info("1/4 获取股票池...")
        codes = self._get_stock_pool(stock_pool, pool_size)
        logger.info(f"   股票池: {len(codes)}只")

        # 2. 获取历史数据
        logger.info("2/4 获取历史K线数据...")
        hist_data = self._get_historical_data(codes, start_date, end_date)
        if len(hist_data) < 10:
            return {'error': '数据不足，至少需要10只有效股票的历史数据'}
        logger.info(f"   有效数据: {len(hist_data)}只")

        # 3. 获取基准数据
        logger.info("3/4 获取基准数据...")
        benchmark = self._get_benchmark_data(start_date, end_date)

        # 4. 运行回测
        logger.info("4/4 运行策略回测...")
        results = {}

        if strategy_type in ('trend', 'both'):
            logger.info("   运行趋势动量策略...")
            results['trend'] = self.backtest_trend_momentum(hist_data, start_date, end_date)

        if strategy_type in ('reversion', 'both'):
            logger.info("   运行超跌反弹策略...")
            results['reversion'] = self.backtest_mean_reversion(hist_data, start_date, end_date)

        # 计算基准收益
        bench_return = 0
        if not benchmark.empty and 'return' in benchmark.columns:
            bench_cumulative = (1 + benchmark['return'].dropna()).cumprod()
            bench_return = round((bench_cumulative.iloc[-1] - 1) * 100, 2) if len(bench_cumulative) > 0 else 0

        for k, v in results.items():
            v['benchmark_return'] = bench_return
            v['excess_return'] = round(v.get('total_return', 0) - bench_return, 2)
            v['stock_pool_size'] = len(hist_data)
            v['period'] = f"{start_date} ~ {end_date}"

        logger.info("✅ 回测完成")
        return results

    def compare_strategies(self, lookback_days: int = 365) -> pd.DataFrame:
        """横向对比多个策略变体"""
        results = self.run_full_backtest('both', lookback_days)

        rows = []
        for name, r in results.items():
            if 'error' in r:
                continue
            rows.append({
                '策略': name,
                '累计收益(%)': r.get('total_return', 0),
                '年化收益(%)': r.get('annual_return', 0),
                '夏普比率': r.get('sharpe_ratio', 0),
                '最大回撤(%)': r.get('max_drawdown', 0),
                '胜率(%)': r.get('win_rate', 0),
                '交易次数': r.get('total_trades', 0),
                '基准收益(%)': r.get('benchmark_return', 0),
                '超额收益(%)': r.get('excess_return', 0),
            })

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values('夏普比率', ascending=False)
        return df

    # ============================================================
    # 指标计算
    # ============================================================

    def _calc_metrics(self, daily_values: List[float], trades: List[Dict],
                       strategy_name: str) -> Dict:
        """计算回测绩效指标"""
        if not daily_values or len(daily_values) < 2:
            return {'strategy_name': strategy_name, 'total_return': 0, 'total_trades': 0}

        values = pd.Series(daily_values)
        daily_rets = values.pct_change().dropna()

        # 累计收益
        total_return = round((values.iloc[-1] - 1) * 100, 2)

        # 年化收益
        days = len(daily_rets)
        annual_return = round(((values.iloc[-1]) ** (252 / max(days, 1)) - 1) * 100, 2)

        # 夏普比率
        if daily_rets.std() > 0:
            excess = daily_rets - 0.02 / 252  # 无风险利率2%
            sharpe = round(excess.mean() / daily_rets.std() * np.sqrt(252), 2)
        else:
            sharpe = 0

        # 最大回撤
        cummax = values.cummax()
        drawdown = (values - cummax) / cummax * 100
        max_dd = round(abs(drawdown.min()), 2)

        # 交易统计
        total_trades = len(trades)
        if trades and total_trades > 0:
            returns = [t.get('return_pct', 0) for t in trades]
            wins = sum(1 for r in returns if r > 0)
            win_rate = round(wins / total_trades * 100, 1)
            avg_win = np.mean([r for r in returns if r > 0]) if wins > 0 else 0
            avg_loss = abs(np.mean([r for r in returns if r < 0])) if wins < total_trades else 1
            profit_loss_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0
        else:
            win_rate = 0
            profit_loss_ratio = 0

        return {
            'strategy_name': strategy_name,
            'total_return': total_return,
            'annual_return': annual_return,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'profit_loss_ratio': profit_loss_ratio,
            'trades': trades[:20],  # 只保留前20笔交易
            'daily_values': [round(v, 4) for v in daily_values[-252:]],  # 最近一年净值
        }


# 单例
real_engine = RealBacktestEngine()
