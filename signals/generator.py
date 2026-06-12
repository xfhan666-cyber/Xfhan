"""
信号生成器 - 综合所有策略，统一产出交易信号
"""
import pandas as pd
from typing import List, Dict
from datetime import datetime
from strategies.base_strategy import TradeSignal, StrategyResult
from strategies.multi_factor import MultiFactorStrategy
from strategies.pb_roe import PBROEStrategy
from strategies.trend_momentum import TrendMomentumStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.smallcap_growth import SmallCapGrowthStrategy
from strategies.limit_up import LimitUpStrategy
from strategies.first_board import FirstBoardStrategy
from data.fetcher import fetcher
from config import DEFAULT_STRATEGY_PARAMS


class SignalGenerator:
    """综合信号生成器"""

    def __init__(self):
        self.strategies = self._init_strategies()
        self.all_signals: List[TradeSignal] = []

    def _init_strategies(self) -> Dict[str, object]:
        """初始化所有策略"""
        return {
            'multi_factor': MultiFactorStrategy(DEFAULT_STRATEGY_PARAMS.get('multi_factor')),
            'pb_roe': PBROEStrategy(DEFAULT_STRATEGY_PARAMS.get('pb_roe')),
            'trend_momentum': TrendMomentumStrategy(DEFAULT_STRATEGY_PARAMS.get('trend_momentum')),
            'mean_reversion': MeanReversionStrategy(DEFAULT_STRATEGY_PARAMS.get('mean_reversion')),
            'smallcap_growth': SmallCapGrowthStrategy(DEFAULT_STRATEGY_PARAMS.get('smallcap_growth')),
            'limit_up': LimitUpStrategy(DEFAULT_STRATEGY_PARAMS.get('limit_up')),
            'first_board': FirstBoardStrategy(DEFAULT_STRATEGY_PARAMS.get('first_board')),
        }

    def run_all_strategies(self, market_data: pd.DataFrame = None,
                           history_data: Dict[str, pd.DataFrame] = None) -> List[TradeSignal]:
        """运行所有策略，收集全部信号"""
        if market_data is None:
            market_data = fetcher.get_realtime_all_stocks()
        if history_data is None:
            history_data = {}

        all_signals = []
        strategy_results: Dict[str, StrategyResult] = {}

        for name, strategy in self.strategies.items():
            try:
                strategy.set_market_data(market_data)
                strategy.set_history_data(history_data)
                result = strategy.run()
                strategy_results[name] = result
                all_signals.extend(result.signals)
            except Exception as e:
                print(f"策略 {name} 运行失败: {e}")

        # 去重 + 合并同股票信号
        merged = self._merge_signals(all_signals)
        self.all_signals = merged
        return merged

    def _merge_signals(self, signals: List[TradeSignal]) -> List[TradeSignal]:
        """合并同股票的多策略信号"""
        if not signals:
            return []

        # 按股票分组
        stock_signals: Dict[str, List[TradeSignal]] = {}
        for s in signals:
            if s.code not in stock_signals:
                stock_signals[s.code] = []
            stock_signals[s.code].append(s)

        merged = []
        for code, sigs in stock_signals.items():
            if len(sigs) >= 2:
                # 多策略共识：提升置信度
                best = max(sigs, key=lambda x: x.confidence)
                strategies = [s.strategy for s in sigs]
                best.confidence = min(98, best.confidence + len(sigs) * 3)
                best.reason += f" | {len(sigs)}个策略同时推荐: {', '.join(strategies)}"
            else:
                best = sigs[0]
            merged.append(best)

        # 按置信度降序
        merged.sort(key=lambda s: s.confidence, reverse=True)
        return merged

    def get_buy_signals(self) -> List[TradeSignal]:
        """获取买入信号"""
        return [s for s in self.all_signals if s.action == 'BUY']

    def get_sell_signals(self) -> List[TradeSignal]:
        """获取卖出信号"""
        return [s for s in self.all_signals if s.action == 'SELL']

    def get_top_picks(self, n: int = 10) -> List[TradeSignal]:
        """获取置信度最高的N个推荐"""
        return sorted(self.get_buy_signals(), key=lambda s: s.confidence, reverse=True)[:n]

    def get_signals_summary(self) -> str:
        """生成信号摘要报告"""
        buys = self.get_buy_signals()
        if not buys:
            return f"[{datetime.now().strftime('%H:%M')}] 当前无买入信号"

        lines = [f"📊 A股量化信号报告 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"]
        lines.append(f"共 {len(buys)} 个买入信号\n")

        for i, s in enumerate(buys[:10], 1):
            lines.append(f"{i}. {s.name}({s.code}) - {s.strategy}")
            lines.append(f"   置信度: {s.confidence:.0f}% | 建议价: {s.price}")
            lines.append(f"   止损: {s.stop_loss} | 止盈: {s.stop_profit}")
            lines.append(f"   理由: {s.reason}")
            lines.append("")

        return '\n'.join(lines)


# 单例
generator = SignalGenerator()
