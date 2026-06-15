"""
超跌反弹策略 — 基于快照数据，无需历史K线
逻辑：跌得够深 + 缩量止跌 + 估值不过分 → 反弹概率高
"""
import numpy as np
import pandas as pd
from typing import List
from strategies.base_strategy import BaseStrategy, TradeSignal


class MeanReversionStrategy(BaseStrategy):
    def __init__(self, params: dict = None):
        default_params = {
            'decline_pct': 10,       # 60日跌幅阈值
            'turnover_max': 3,       # 换手率上限（缩量）
            'stop_profit_pct': 5,    # 止盈5%
            'stop_loss_pct': 3,      # 止损3%
            'max_hold_days': 5,      # 最大持有天数
        }
        merged = {**default_params, **({} if params is None else params)}
        super().__init__(
            name='超跌反弹',
            description='寻找严重超跌后缩量止跌的反弹机会，快进快出，每笔风险可控',
            params=merged
        )

    def filter_stocks(self) -> pd.DataFrame:
        df = self.filter_st_basic(self.market_data)
        if df.empty:
            return df
        # 排除北交所、成交额太低的无流动性股
        df = df[~df['code'].str.startswith(('688', '8', '4'), na=False)]
        df = df[df['amount'] > 5e7]  # 日成交额>5000万
        df = df[df['market_cap'] > 3e9]  # 市值>30亿
        return df

    def rank_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        data_quality = df['_data_quality'].iloc[0] if '_data_quality' in df.columns else 'unknown'

        # 使用快照数据中的60日涨跌幅
        if 'pct_60d' not in df.columns:
            return pd.DataFrame()

        # 根据数据质量调整阈值
        if data_quality == 'full':
            decline_threshold = self.params['decline_pct']
        else:
            # 新浪估算数据：pct_60d=当日涨跌×6，不太准，适当放宽
            decline_threshold = self.params['decline_pct'] * 0.5  # 5%即可触发

        # 筛选超跌
        df = df[df['pct_60d'] <= -decline_threshold].copy()
        if df.empty:
            return df

        # 今日不能继续大跌（止跌信号），但允许小跌
        df = df[df['pct_change'] > -7]

        # 缩量筛选：换手率不宜过高
        if 'turnover' in df.columns:
            turnover_max = self.params['turnover_max'] + 2 if data_quality != 'full' else self.params['turnover_max']
            df = df[df['turnover'] <= turnover_max]

        # 评分
        df['score'] = (
            df['pct_60d'].apply(lambda x: min(50, abs(x) / max(abs(decline_threshold), 1) * 25)) +
            df['turnover'].apply(lambda x: max(0, (5 - x) * 6)) +
            df['pct_change'].apply(lambda x: max(0, x + 5) * 4)  # 止跌确认
        )

        df = df.sort_values('score', ascending=False)
        return df.head(20)

    def generate_signals(self, ranked_df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        for _, row in ranked_df.head(8).iterrows():
            price = row['price']
            decline = abs(row.get('pct_60d', 0))
            turnover = row.get('turnover', 0)
            vol_ratio = row.get('volume_ratio', 1)
            pe = row.get('pe_ratio', 0)

            # 构建触发原因
            trigger_parts = [f'60日跌{decline:.0f}%（超跌确认）']
            if turnover <= 1:
                trigger_parts.append('换手率极低，抛压衰竭')
            elif turnover <= self.params['turnover_max']:
                trigger_parts.append(f'换手率{turnover:.1f}%，缩量止跌')
            if row.get('pct_change', -99) > -2:
                trigger_parts.append('今日跌幅收窄，止跌信号')
            if 0 < pe < 30:
                trigger_parts.append(f'PE={pe:.0f}，估值合理')
            elif pe <= 0:
                trigger_parts.append('⚠️亏损股，注意风险')

            signals.append(TradeSignal(
                code=str(row['code']), name=str(row['name']),
                action='BUY', strategy=self.name, price=price,
                confidence=round(min(80, row['score'] * 0.8), 1),
                reason='；'.join(trigger_parts),
                stop_loss=round(price * (1 - self.params['stop_loss_pct'] / 100), 2),
                stop_profit=round(price * (1 + self.params['stop_profit_pct'] / 100), 2),
                factors={
                    'decline_60d': round(decline, 1),
                    'turnover': round(turnover, 1),
                    'vol_ratio': round(vol_ratio, 1),
                    'today_pct': round(row.get('pct_change', 0), 1),
                    'score': round(row['score'], 1),
                    'pe': round(pe, 1) if pe > 0 else '亏损',
                }
            ))
        return signals
