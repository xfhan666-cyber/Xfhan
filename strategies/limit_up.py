"""
策略6：涨停板跟踪策略
分析涨停板质量，筛选有连板潜力的首板
"""
import numpy as np
import pandas as pd
from typing import List
from strategies.base_strategy import BaseStrategy, TradeSignal


class LimitUpStrategy(BaseStrategy):
    def __init__(self, params: dict = None):
        default_params = {
            'seal_time_min': 60,
            'seal_fund_ratio': 0.01,
            'max_open_pct': 5
        }
        merged = {**default_params, **({} if params is None else params)}
        super().__init__(
            name='涨停板跟踪',
            description='筛选高质量首板，博弈次日连板机会',
            params=merged
        )

    def filter_stocks(self) -> pd.DataFrame:
        df = self.market_data
        if df is None or df.empty:
            return df
        df = self.filter_st_basic(df)
        # 只保留今日涨停的股票
        df = df[df['pct_change'] >= 9.8]
        # 排除一字板（开盘即涨停，今开=昨日收盘价*1.1左右）
        if 'open' in df.columns and 'pre_close' in df.columns:
            df['is_yizi'] = df['open'] >= df['pre_close'] * 1.09
            df = df[~df['is_yizi']]
        return df

    def rank_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        scores = pd.DataFrame(index=df.index)
        scores['code'] = df['code']
        scores['name'] = df['name']

        # 封板早晚（用振幅代理 - 振幅小说明封板早）
        if 'amplitude' in df.columns:
            scores['seal_score'] = (15 - df['amplitude']).clip(0, 15) / 15 * 100
        else:
            scores['seal_score'] = 50

        # 成交额（成交额适中较好）
        if 'amount' in df.columns:
            median = df['amount'].median()
            scores['amount_score'] = (1 - abs(df['amount'] - median) / median).clip(0, 1) * 100
        else:
            scores['amount_score'] = 50

        # 换手率适中
        if 'turnover' in df.columns:
            scores['turnover_score'] = (15 - abs(df['turnover'] - 5)).clip(0, 15) / 15 * 100
        else:
            scores['turnover_score'] = 50

        # 市值小加分
        if 'market_cap' in df.columns:
            scores['cap_score'] = df['market_cap'].rank(ascending=True, pct=True) * 100
        else:
            scores['cap_score'] = 50

        scores['score'] = (
            scores['seal_score'] * 0.35 +
            scores['amount_score'] * 0.15 +
            scores['turnover_score'] * 0.20 +
            scores['cap_score'] * 0.30
        )

        result = df.copy()
        result['score'] = scores['score']
        result = result.sort_values('score', ascending=False)
        return result.head(15)

    def generate_signals(self, ranked_df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        for _, row in ranked_df.head(8).iterrows():
            price = row['price']
            cap = row.get('market_cap', 0) / 1e8
            signals.append(TradeSignal(
                code=str(row['code']), name=str(row['name']),
                action='BUY', strategy=self.name, price=price,
                confidence=round(min(75, row.get('score', 50) * 0.72), 1),
                reason=(f"今日涨停板，振幅{row.get('amplitude','?')}%封板质量高，" +
                       f"市值{cap:.0f}亿，换手{row.get('turnover','?')}%，博弈次日惯性冲高"),
                stop_loss=round(price * 0.95, 2),
                stop_profit=round(price * 1.08, 2),
                factors={'amplitude': row.get('amplitude', 0), 'score': round(row.get('score', 0), 1)}
            ))
        return signals
