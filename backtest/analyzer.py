"""
回测结果分析器 - 计算夏普比率、最大回撤、胜率、年化收益等指标
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List


@dataclass
class BacktestResult:
    """回测结果"""
    strategy_name: str
    total_return: float = 0        # 累计收益率(%)
    annual_return: float = 0       # 年化收益率(%)
    sharpe_ratio: float = 0        # 夏普比率
    max_drawdown: float = 0        # 最大回撤(%)
    win_rate: float = 0            # 胜率(%)
    total_trades: int = 0          # 总交易次数
    profit_loss_ratio: float = 0   # 盈亏比
    benchmark_return: float = 0    # 基准收益率(%)
    excess_return: float = 0       # 超额收益(%)
    monthly_returns: List[float] = field(default_factory=list)
    daily_values: List[float] = field(default_factory=list)
    trade_log: pd.DataFrame = field(default_factory=pd.DataFrame)


class BacktestAnalyzer:
    """回测结果计算器"""

    @staticmethod
    def calculate_from_returns(daily_returns: pd.Series, benchmark_returns: pd.Series = None,
                                strategy_name: str = '', trades: pd.DataFrame = None) -> BacktestResult:
        """从日收益率序列计算回测指标"""
        if daily_returns.empty:
            return BacktestResult(strategy_name=strategy_name)

        result = BacktestResult(strategy_name=strategy_name)

        # 累计净值
        cumulative = (1 + daily_returns / 100).cumprod()
        result.total_return = round((cumulative.iloc[-1] - 1) * 100, 2)
        result.daily_values = cumulative.tolist()

        # 年化收益率（约252个交易日）
        days = len(daily_returns)
        if days > 0:
            result.annual_return = round(((cumulative.iloc[-1]) ** (252 / days) - 1) * 100, 2)

        # 夏普比率（假设无风险利率2%）
        if daily_returns.std() > 0:
            excess = daily_returns - 2 / 252
            result.sharpe_ratio = round(excess.mean() / daily_returns.std() * np.sqrt(252), 2)

        # 最大回撤
        cummax = cumulative.cummax()
        drawdown = (cumulative - cummax) / cummax * 100
        result.max_drawdown = round(abs(drawdown.min()), 2)

        # 月度收益（需要DatetimeIndex，否则用简单分组）
        try:
            if len(daily_returns) >= 20:
                if isinstance(daily_returns.index, pd.DatetimeIndex):
                    monthly = daily_returns.resample('ME').apply(lambda x: (1 + x / 100).prod() - 1) * 100
                else:
                    # 非时间索引，每20个交易日为一组
                    monthly = daily_returns.groupby(daily_returns.index // 20).apply(lambda x: (1 + x / 100).prod() - 1) * 100
                result.monthly_returns = [round(r, 2) for r in monthly.tolist()]
        except Exception:
            result.monthly_returns = []

        # 交易统计（如果有交易记录）
        if trades is not None and not trades.empty:
            result.total_trades = len(trades)
            if 'pnl' in trades.columns:
                wins = len(trades[trades['pnl'] > 0])
                result.win_rate = round(wins / result.total_trades * 100, 2) if result.total_trades > 0 else 0
                avg_win = trades[trades['pnl'] > 0]['pnl'].mean() if wins > 0 else 0
                avg_loss = abs(trades[trades['pnl'] < 0]['pnl'].mean()) if wins < result.total_trades else 1
                result.profit_loss_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0
            result.trade_log = trades

        # 基准对比
        if benchmark_returns is not None and not benchmark_returns.empty:
            bench_cum = (1 + benchmark_returns / 100).cumprod()
            result.benchmark_return = round((bench_cum.iloc[-1] - 1) * 100, 2)
            result.excess_return = round(result.total_return - result.benchmark_return, 2)

        return result

    @staticmethod
    def calculate_from_signals(signals: list, price_data: dict) -> BacktestResult:
        """从买卖信号模拟回测结果"""
        returns_list = []
        trades_list = []

        for signal in signals:
            if signal.action != 'BUY':
                continue
            code = signal.code
            if code not in price_data:
                continue

            df_hist = price_data[code]
            if df_hist is None or df_hist.empty:
                continue

            # 简单回测：假设按信号价格买入，N天后按止盈/止损/时间卖出
            entry_price = signal.price
            stop_loss = signal.stop_loss
            stop_profit = signal.stop_profit

            # 找信号日之后的价格走势
            signal_date = signal.timestamp.split(' ')[0]
            future = df_hist[df_hist['date'] >= signal_date]

            if len(future) < 2:
                continue

            exit_price = entry_price
            exit_date = signal_date
            for _, bar in future.iterrows():
                if bar['low'] <= stop_loss:
                    exit_price = stop_loss
                    exit_date = bar['date']
                    break
                if bar['high'] >= stop_profit:
                    exit_price = stop_profit
                    exit_date = bar['date']
                    break
                exit_price = bar['close']
                exit_date = bar['date']

            pnl_pct = (exit_price / entry_price - 1) * 100
            returns_list.append(pnl_pct)
            trades_list.append({
                'code': code, 'entry_date': signal_date,
                'exit_date': exit_date, 'entry_price': entry_price,
                'exit_price': exit_price, 'pnl': round(pnl_pct, 2)
            })

        if not returns_list:
            return BacktestResult(strategy_name='信号回测')

        daily_returns = pd.Series(returns_list, name='returns')
        trades_df = pd.DataFrame(trades_list)
        return BacktestAnalyzer.calculate_from_returns(daily_returns, None, '信号模拟回测', trades_df)

    @staticmethod
    def compare_strategies(results: List[BacktestResult]) -> pd.DataFrame:
        """对比多个策略"""
        rows = []
        for r in results:
            rows.append({
                '策略': r.strategy_name,
                '累计收益(%)': r.total_return,
                '年化收益(%)': r.annual_return,
                '夏普比率': r.sharpe_ratio,
                '最大回撤(%)': r.max_drawdown,
                '胜率(%)': r.win_rate,
                '超额收益(%)': r.excess_return,
                '交易次数': r.total_trades,
                '盈亏比': r.profit_loss_ratio,
            })
        return pd.DataFrame(rows).sort_values('夏普比率', ascending=False)
