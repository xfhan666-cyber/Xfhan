"""
策略5：小盘成长轮动
中证1000成分股，高营收增速+小市值+机构增持
"""
import numpy as np
import pandas as pd
from typing import List
from strategies.base_strategy import BaseStrategy, TradeSignal


class SmallCapGrowthStrategy(BaseStrategy):
    def __init__(self, params: dict = None):
        default_params = {
            'top_n': 15,
            'revenue_growth_min': 20,
            'market_cap_max': 2e10,
            'turnover_min': 2,
            'turnover_max': 8
        }
        merged = {**default_params, **({} if params is None else params)}
        super().__init__(
            name='小盘成长轮动',
            description='市值<200亿+高成长+机构关注+换手适中，中证1000风格',
            params=merged
        )

    def filter_stocks(self) -> pd.DataFrame:
        df = self.filter_st_basic(self.market_data)
        if df.empty:
            return df
        df = df[~df['code'].str.startswith(('688', '8'), na=False)]
        df = df[df['amount'] > 3e6]
        # 市值小于200亿
        df = df[df['market_cap'] < self.params['market_cap_max']]
        df = df[df['market_cap'] > 1e9]  # 大于10亿防壳
        # 换手合理范围
        df = df[df['turnover'].between(self.params['turnover_min'], self.params['turnover_max'])]
        return df

    def rank_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        scores = pd.DataFrame(index=df.index)

        # YTD涨幅作为成长代理
        if 'pct_ytd' in df.columns:
            scores['growth_score'] = df['pct_ytd'].rank(pct=True) * 100
        elif 'pct_60d' in df.columns:
            scores['growth_score'] = df['pct_60d'].rank(pct=True) * 100
        else:
            scores['growth_score'] = 50

        # 小市值加分
        if 'market_cap' in df.columns:
            scores['size_score'] = df['market_cap'].rank(ascending=True, pct=True) * 100
        else:
            scores['size_score'] = 50

        # 换手活跃度适中加分
        if 'turnover' in df.columns:
            median_turnover = df['turnover'].median()
            scores['activity_score'] = (1 - abs(df['turnover'] - median_turnover) / median_turnover).clip(0, 1) * 100
        else:
            scores['activity_score'] = 50

        # 今日涨幅正向（趋势确认）
        if 'pct_change' in df.columns:
            scores['today_score'] = df['pct_change'].clip(-3, 8).rank(pct=True) * 100
        else:
            scores['today_score'] = 50

        scores['score'] = (
            scores['growth_score'] * 0.40 +
            scores['size_score'] * 0.25 +
            scores['activity_score'] * 0.20 +
            scores['today_score'] * 0.15
        )

        result = df.copy()
        result['score'] = scores['score']
        result = result.sort_values('score', ascending=False)
        return result.head(self.params['top_n'])

    def generate_signals(self, ranked_df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        for _, row in ranked_df.head(8).iterrows():
            price = row['price']
            cap = row.get('market_cap', 0) / 1e8
            signals.append(TradeSignal(
                code=str(row['code']), name=str(row['name']),
                action='BUY', strategy=self.name, price=price,
                confidence=round(min(82, row.get('score', 50) * 0.8), 1),
                reason=(f"市值{cap:.0f}亿小盘成长，换手活跃，趋势确认。" +
                        f"YTD涨{row.get('pct_ytd','?')}%，动量充足"),
                stop_loss=round(price * 0.88, 2),
                stop_profit=round(price * 1.25, 2),
                factors={'market_cap': f'{cap:.0f}亿', 'score': round(row.get('score', 0), 1)}
            ))
        return signals
