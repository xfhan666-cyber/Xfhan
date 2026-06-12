"""
策略2：PB-ROE价值精选
寻找低PB+高ROE+盈利稳定的优质价值股
"""
import numpy as np
import pandas as pd
from typing import List
from strategies.base_strategy import BaseStrategy, TradeSignal


class PBROEStrategy(BaseStrategy):
    def __init__(self, params: dict = None):
        default_params = {
            'top_n': 20,
            'pb_threshold': 0.8,
            'roe_min': 15,
            'roe_std_max': 5,
            'min_volume': 5e7
        }
        merged = {**default_params, **({} if params is None else params)}
        super().__init__(
            name='PB-ROE价值精选',
            description=f'PB<行业均值×{merged["pb_threshold"]}, ROE>{merged["roe_min"]}%, 盈利稳定, 按ROE/PB排名',
            params=merged
        )

    def filter_stocks(self) -> pd.DataFrame:
        df = self.filter_st_basic(self.market_data)
        if df.empty:
            return df
        df = df[~df['code'].str.startswith('8', na=False)]
        df = df[df['amount'] > self.params['min_volume']]

        # PB筛选：PB>0且低于阈值
        df = df[(df['pb_ratio'] > 0) & (df['pb_ratio'] < 10)]

        return df

    def rank_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        # 计算行业平均PB
        df['industry_pb_avg'] = df.groupby('industry')['pb_ratio'].transform('mean') if 'industry' in df.columns else df['pb_ratio'].mean()

        # PB低于行业平均×阈值
        df = df[df['pb_ratio'] < df['industry_pb_avg'] * self.params['pb_threshold']]

        # ROE筛选（如果有）
        if 'roe' in df.columns:
            df = df[df['roe'] >= self.params['roe_min']]

        # ROE/PB 性价比排名
        df['roe_pb_ratio'] = np.where(
            df['pb_ratio'] > 0,
            df.get('roe', df.get('pe_ratio', 1).apply(lambda x: 100 / x if x and x > 0 else 10)) / df['pb_ratio'],
            0
        )

        df['score'] = df['roe_pb_ratio'].rank(pct=True) * 100
        df = df.sort_values('score', ascending=False)

        return df.head(self.params['top_n'])

    def generate_signals(self, ranked_df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        for _, row in ranked_df.head(8).iterrows():
            price = row.get('price', 0)
            pb = row.get('pb_ratio', 'N/A')
            signals.append(TradeSignal(
                code=str(row['code']), name=str(row['name']),
                action='BUY', strategy=self.name, price=price,
                confidence=round(min(90, row.get('score', 50) * 0.85), 1),
                reason=f"PB={pb}低于行业均值，ROE/PB性价比排名前列，价值洼地发现",
                stop_loss=round(price * 0.90, 2),
                stop_profit=round(price * 1.30, 2),
                factors={'pb': pb, 'score': round(row.get('score', 0), 1)}
            ))
        return signals
