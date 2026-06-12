"""
回测引擎 - 封装Backtrader + 简化版回测
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from data.fetcher import fetcher
from backtest.analyzer import BacktestAnalyzer, BacktestResult


class SimpleBacktestEngine:
    """简化回测引擎 - 不依赖Backtrader，直接用pandas实现"""

    def __init__(self):
        self.analyzer = BacktestAnalyzer()

    def run_strategy_backtest(self, strategy_instance, stock_pool: list = None,
                               start_date: str = None, end_date: str = None,
                               benchmark_code: str = '000300') -> BacktestResult:
        """运行策略历史回测"""
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
        if end_date is None:
            end_date = datetime.now().strftime('%Y%m%d')

        # 获取历史数据
        if stock_pool is None:
            # 默认用沪深300成分股池
            stock_pool = []

        # 获取基准数据
        benchmark_data = None
        try:
            benchmark_data = fetcher.get_daily_kline(benchmark_code, start_date=start_date, end_date=end_date)
        except Exception:
            pass

        # 简化回测：逐月调仓模拟
        all_returns = []
        all_trades = []

        if stock_pool:
            for code in stock_pool[:50]:  # 限制股票数量
                df = fetcher.get_daily_kline(code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty and len(df) > 60:
                    # 计算策略信号的简版
                    df['ma_20'] = df['close'].rolling(20).mean()
                    df['ma_60'] = df['close'].rolling(60).mean()
                    df['signal'] = (df['ma_20'] > df['ma_60']).astype(int)
                    df['position'] = df['signal'].diff()
                    df['return'] = df['close'].pct_change() * 100 * df['signal'].shift(1)
                    all_returns.append(df['return'].dropna())

        if all_returns:
            combined = pd.concat(all_returns, axis=1).mean(axis=1)
            combined = combined.dropna()

            benchmark_returns = None
            if benchmark_data is not None and not benchmark_data.empty:
                benchmark_returns = benchmark_data['close'].pct_change() * 100
                benchmark_returns.index = combined.index[:len(benchmark_returns)]

            return self.analyzer.calculate_from_returns(combined, benchmark_returns, strategy_instance.name)
        return BacktestResult(strategy_name=strategy_instance.name)

    def run_backtest_comparison(self, strategies: list, days: int = 250) -> list:
        """对比多个策略的回测表现"""
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        results = []
        for strategy in strategies:
            result = self.run_strategy_backtest(strategy, start_date=start_date, end_date=end_date)
            results.append(result)

        return results

    def generate_sample_backtest(self, strategy_name: str) -> BacktestResult:
        """生成示例回测结果（用于演示，实际使用时替换为真实回测）"""
        # 基于真实统计数据的模拟回测
        np.random.seed(hash(strategy_name) % (2**31))

        days = 250
        daily_returns = pd.Series(np.random.normal(0.08, 1.2, days), name='returns')
        benchmark = pd.Series(np.random.normal(0.03, 1.0, days), name='benchmark')

        # 策略特定的调整
        if '多因子' in strategy_name:
            daily_returns += 0.02
        elif 'PB-ROE' in strategy_name:
            daily_returns += 0.015
        elif '趋势' in strategy_name:
            daily_returns += 0.025
            daily_returns.iloc[-60:] -= 0.01  # 趋势策略近期衰减
        elif '反弹' in strategy_name:
            daily_returns += 0.01
        elif '小盘' in strategy_name:
            daily_returns += 0.03
            daily_returns *= 1.2
        elif '涨停' in strategy_name:
            daily_returns += 0.04
            daily_returns *= 1.5

        # 模拟交易
        trades = pd.DataFrame({
            'code': [f'{600000 + i}' for i in range(30)],
            'entry_date': pd.date_range(end=datetime.now(), periods=30),
            'exit_date': pd.date_range(end=datetime.now() + timedelta(days=15), periods=30),
            'pnl': np.random.normal(3, 5, 30)
        })

        return self.analyzer.calculate_from_returns(daily_returns, benchmark, strategy_name, trades)


# 单例
engine = SimpleBacktestEngine()
