"""
趋势动量策略 — 基于快照数据，无需历史K线
逻辑：放量上涨 + 资金流入 + 趋势确认 → 顺势跟随
"""
import numpy as np
import pandas as pd
from typing import List
from strategies.base_strategy import BaseStrategy, TradeSignal


class TrendMomentumStrategy(BaseStrategy):
    def __init__(self, params: dict = None):
        default_params = {
            'volume_ratio': 1.5,         # 量比阈值
            'pct_min': 1.0,              # 今日最低涨幅
            'amount_min': 5e7,           # 最低成交额（过滤无流动性）
            'turnover_min': 2,           # 最低换手率（要有活跃度）
            'turnover_max': 15,          # 最高换手率（排除异常放量）
            'stop_loss_pct': 8,          # 止损幅度
            'bull_market_bonus': 5,      # 强势市场加分
        }
        merged = {**default_params, **({} if params is None else params)}
        super().__init__(
            name='趋势动量+资金流',
            description='放量上涨+资金流入+趋势确认，顺势而为，中短线3-10天持有',
            params=merged
        )

    def filter_stocks(self) -> pd.DataFrame:
        df = self.filter_st_basic(self.market_data)
        if df.empty:
            return df
        # 排除北交所、创业板（波动大）
        df = df[~df['code'].str.startswith(('688', '8', '4', '300'), na=False)]
        # 流动性门槛
        df = df[df['amount'] > self.params['amount_min']]
        # 今日必须上涨
        df = df[df['pct_change'] >= self.params['pct_min']]
        return df

    def rank_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        # 检查数据质量，调整阈值
        data_quality = df['_data_quality'].iloc[0] if '_data_quality' in df.columns else 'unknown'
        # 新浪数据源volume_ratio默认为1.0（不准确），降低阈值
        vr_threshold = self.params['volume_ratio'] if data_quality == 'full' else 0.8

        # 量比筛选：放量才有趋势意义
        if 'volume_ratio' in df.columns:
            df = df[df['volume_ratio'] >= vr_threshold]

        # 换手率筛选：太冷清或太疯狂都不好
        if 'turnover' in df.columns:
            df = df[(df['turnover'] >= self.params['turnover_min']) &
                    (df['turnover'] <= self.params['turnover_max'])]

        if df.empty:
            return df

        # 趋势强度评分
        df['score'] = (
            # 今日涨幅贡献（0-30分）
            df['pct_change'].apply(lambda x: min(30, max(0, x) * 5)) +
            # 量比贡献（0-25分）：放量越大越好但有上限
            df['volume_ratio'].apply(lambda x: min(25, x * 10)) +
            # 成交额贡献（0-20分）：大资金关注
            df['amount'].apply(lambda x: min(20, np.log10(max(x, 1e6)) - 6)) +
            # 换手率适中（0-15分）：2-8%最佳
            df['turnover'].apply(lambda x: 15 if 2 <= x <= 8 else max(0, 15 - abs(x-5)*2)) +
            # 振幅贡献（0-10分）：有一定振幅说明资金活跃
            df['amplitude'].apply(lambda x: min(10, x * 2) if pd.notna(x) else 5)
        )

        # 60日趋势加分：之前涨过的更容易继续涨
        if 'pct_60d' in df.columns:
            df['score'] += df['pct_60d'].apply(
                lambda x: min(10, max(0, x / 3)) if x > 0 else max(-10, x / 5)
            )

        df = df.sort_values('score', ascending=False)
        return df.head(20)

    def generate_signals(self, ranked_df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        for _, row in ranked_df.head(10).iterrows():
            price = row['price']
            pct = row.get('pct_change', 0)
            vol_ratio = row.get('volume_ratio', 1)
            turnover = row.get('turnover', 0)
            amount = row.get('amount', 0) / 1e8  # 转为亿
            amp = row.get('amplitude', 0)

            trigger_parts = []
            trigger_parts.append(f'今日涨{pct:.1f}%，量比{vol_ratio:.1f}倍放量上攻')
            trigger_parts.append(f'成交额{amount:.1f}亿，换手率{turnover:.1f}%')
            if pd.notna(amp) and amp > 3:
                trigger_parts.append(f'振幅{amp:.1f}%，资金博弈活跃')

            pe = row.get('pe_ratio', 0)
            pb = row.get('pb_ratio', 0)
            if 0 < pe < 40:
                trigger_parts.append(f'PE={pe:.0f}，估值适中')
            elif pe > 40:
                trigger_parts.append(f'⚠️PE={pe:.0f}偏高')

            signals.append(TradeSignal(
                code=str(row['code']), name=str(row['name']),
                action='BUY', strategy=self.name, price=price,
                confidence=round(min(85, row['score'] * 0.85), 1),
                reason='；'.join(trigger_parts),
                stop_loss=round(price * (1 - self.params['stop_loss_pct'] / 100), 2),
                stop_profit=round(price * 1.12, 2),
                factors={
                    'pct_today': round(pct, 1),
                    'vol_ratio': round(vol_ratio, 1),
                    'turnover': round(turnover, 1),
                    'amount_yi': round(amount, 1),
                    'amplitude': round(amp, 1) if pd.notna(amp) else 0,
                    'score': round(row['score'], 1),
                }
            ))
        return signals
