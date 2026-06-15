"""
市场环境判断 — A股情绪市+政策市+散户市的量化刻画

核心理念：
- A股不是有效市场，情绪和政策是最大驱动力
- 牛市多做（放大仓位），熊市少做（缩小仓位或空仓）
- 别人贪婪我恐惧（极端情绪反转）

输出：
- 市场状态：🔥狂热 / 🟢强势 / 🟡震荡 / 🟠弱势 / 🔴冰点
- 建议仓位：0%-100%
- 策略权重：趋势/低吸/价值的动态配比
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class MarketRegime:
    """市场环境快照"""
    status: str = 'unknown'       # 市场状态
    status_emoji: str = '❓'
    score: float = 50             # 综合评分(0-100)
    suggested_position: float = 0.5  # 建议仓位(0-1)

    # 各项指标
    breadth: float = 0            # 涨跌比(%)
    limit_up_count: int = 0       # 涨停数
    limit_down_count: int = 0     # 跌停数
    total_amount: float = 0       # 成交额(亿)
    avg_pct: float = 0            # 平均涨跌(%)
    index_trend: str = 'flat'     # 指数趋势
    sentiment: str = 'neutral'    # 市场情绪
    fear_greed_index: float = 50  # 恐惧贪婪指数(0=极度恐惧,100=极度贪婪)

    # 策略建议
    strategy_weights: Dict[str, float] = field(default_factory=dict)
    advice: List[str] = field(default_factory=list)


class MarketRegimeDetector:
    """
    市场温度计

    判断依据：
    1. 涨跌比（市场广度）— A股散户情绪的直接体现
    2. 涨停/跌停数量 — 极端情绪的量化指标
    3. 成交额 — 资金参与度
    4. 恐惧贪婪指数 — 逆向指标
    5. 指数趋势 — 大盘方向
    """

    def detect(self, market_df: pd.DataFrame,
               index_data: pd.DataFrame = None) -> MarketRegime:
        """
        从全市场快照数据判断当前市场状态
        """
        regime = MarketRegime()
        total = len(market_df)

        if total == 0:
            return regime

        # === 1. 市场广度（涨跌比）===
        up = len(market_df[market_df['pct_change'] > 0])
        down = len(market_df[market_df['pct_change'] < 0])
        flat = total - up - down
        regime.breadth = round(up / total * 100, 1)

        # === 2. 极端情绪（涨跌停）===
        regime.limit_up_count = len(market_df[market_df['pct_change'] >= 9.8])
        regime.limit_down_count = len(market_df[market_df['pct_change'] <= -9.8])

        # === 3. 资金参与度 ===
        if 'amount' in market_df.columns:
            regime.total_amount = round(market_df['amount'].sum() / 1e8, 0)  # 亿
        regime.avg_pct = round(market_df['pct_change'].mean(), 2)

        # === 4. 恐惧贪婪指数 ===
        regime.fear_greed_index = self._calc_fear_greed(market_df)

        # === 5. 综合评分 ===
        score = 50  # 基准分

        # 涨跌比贡献（-25 ~ +25）
        if regime.breadth > 70:
            score += 20
        elif regime.breadth > 55:
            score += 10
        elif regime.breadth > 40:
            score += 0
        elif regime.breadth > 25:
            score -= 10
        else:
            score -= 20

        # 涨停/跌停贡献（-15 ~ +15）
        if regime.limit_up_count > 80:
            score += 15  # 百股涨停，情绪高涨
        elif regime.limit_up_count > 50:
            score += 8
        elif regime.limit_up_count < 20:
            score -= 5

        if regime.limit_down_count > 30:
            score -= 15  # 恐慌杀跌
        elif regime.limit_down_count > 10:
            score -= 8

        # 成交额贡献（-10 ~ +10）
        if regime.total_amount > 15000:
            score += 10  # 放量
        elif regime.total_amount > 8000:
            score += 5
        elif regime.total_amount < 5000:
            score -= 5  # 缩量观望

        # 恐惧贪婪逆向指标：过于贪婪→减分，过于恐惧→加分（别人贪婪我恐惧）
        if regime.fear_greed_index > 80:
            score -= 15  # 极度贪婪，警惕见顶
            regime.advice.append('市场极度贪婪，注意风险，随时准备减仓')
        elif regime.fear_greed_index > 65:
            score -= 5
        elif regime.fear_greed_index < 20:
            score += 15  # 极度恐惧，机会来临
            regime.advice.append('市场极度恐惧，别人恐惧我贪婪，可逐步加仓')
        elif regime.fear_greed_index < 35:
            score += 5

        regime.score = max(0, min(100, score))

        # === 6. 确定市场状态 ===
        if regime.score >= 80:
            regime.status = '🔥 狂热'
            regime.status_emoji = '🔥'
            regime.suggested_position = 0.7
            regime.sentiment = 'greedy'
            regime.advice.append('强势市场，趋势策略优先，注意高位风险')
        elif regime.score >= 60:
            regime.status = '🟢 强势'
            regime.status_emoji = '🟢'
            regime.suggested_position = 0.8
            regime.sentiment = 'bullish'
            regime.advice.append('市场环境良好，趋势动量策略占主导')
        elif regime.score >= 40:
            regime.status = '🟡 震荡'
            regime.status_emoji = '🟡'
            regime.suggested_position = 0.5
            regime.sentiment = 'neutral'
            regime.advice.append('震荡市，低吸策略+趋势策略各半，控制仓位')
        elif regime.score >= 20:
            regime.status = '🟠 弱势'
            regime.status_emoji = '🟠'
            regime.suggested_position = 0.3
            regime.sentiment = 'bearish'
            regime.advice.append('弱势市场，超跌反弹策略为主，严格止损')
        else:
            regime.status = '🔴 冰点'
            regime.status_emoji = '🔴'
            regime.suggested_position = 0.1
            regime.sentiment = 'fearful'
            regime.advice.append('极端弱势，建议空仓观望或仅小仓位试探')

        # === 7. 策略权重建议 ===
        if regime.sentiment in ('bullish', 'greedy'):
            # 强势：趋势为主，低吸为辅
            regime.strategy_weights = {
                'trend_momentum': 0.55,
                'mean_reversion': 0.25,
                'pb_roe': 0.20,
            }
        elif regime.sentiment == 'neutral':
            # 震荡：均衡
            regime.strategy_weights = {
                'trend_momentum': 0.35,
                'mean_reversion': 0.35,
                'pb_roe': 0.30,
            }
        else:
            # 弱势：低吸为主，防御优先
            regime.strategy_weights = {
                'trend_momentum': 0.15,
                'mean_reversion': 0.50,
                'pb_roe': 0.35,
            }

        return regime

    def _calc_fear_greed(self, df: pd.DataFrame) -> float:
        """
        简易恐惧贪婪指数(0-100)

        0 = 极度恐惧（买点）
        100 = 极度贪婪（卖点）

        组成：
        - 涨跌比偏离度（vs 50%）
        - 涨停/跌停比
        - 5%以上涨幅占比
        - 5%以上跌幅占比
        """
        total = len(df)
        if total == 0:
            return 50

        # 涨跌比分量
        up_ratio = len(df[df['pct_change'] > 0]) / total
        breadth_score = up_ratio * 100

        # 极端涨幅分量
        surge_ratio = len(df[df['pct_change'] > 5]) / total * 100
        plunge_ratio = len(df[df['pct_change'] < -5]) / total * 100

        # 涨停跌停比
        limit_up = len(df[df['pct_change'] >= 9.8])
        limit_down = len(df[df['pct_change'] <= -9.8])
        if limit_down > 0:
            lu_ld_ratio = limit_up / (limit_up + limit_down)
        else:
            lu_ld_ratio = 1.0 if limit_up > 0 else 0.5

        # 综合
        index = (
            breadth_score * 0.3 +
            lu_ld_ratio * 100 * 0.3 +
            min(surge_ratio * 10, 100) * 0.2 +
            max(100 - plunge_ratio * 10, 0) * 0.2
        )

        return round(max(0, min(100, index)), 1)

    def format_display(self, regime: MarketRegime) -> str:
        """格式化市场环境显示"""
        return (
            f"## {regime.status_emoji} 市场温度计\n\n"
            f"**状态**: {regime.status} (评分: {regime.score}/100)\n\n"
            f"**建议仓位**: {regime.suggested_position*100:.0f}%\n\n"
            f"**涨跌比**: {regime.breadth}%上涨 | "
            f"涨停{regime.limit_up_count}家 | 跌停{regime.limit_down_count}家 | "
            f"成交{regime.total_amount:.0f}亿\n\n"
            f"**恐惧贪婪**: {regime.fear_greed_index}/100\n\n"
            f"**策略建议**: {', '.join(regime.advice)}"
        )


# 单例
regime_detector = MarketRegimeDetector()
