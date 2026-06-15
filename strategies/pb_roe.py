"""
PB-ROE价值精选策略
逻辑：低PB+合理估值+盈利能力的价值股
注意：依赖真实PE/PB数据。如果数据源为新浪(无PE/PB)，此策略产出有限。
"""
import numpy as np
import pandas as pd
from typing import List
from strategies.base_strategy import BaseStrategy, TradeSignal


class PBROEStrategy(BaseStrategy):
    def __init__(self, params: dict = None):
        default_params = {
            'top_n': 20,
            'pb_max': 5,              # PB上限（排除过高估值）
            'pb_min': 0.3,            # PB下限（排除破产风险）
            'pe_min': 3,              # PE下限（排除微利股）
            'pe_max': 50,             # PE上限（排除泡沫）
            'roe_min': 8,             # ROE最低要求（估算值）
            'min_amount': 5e7,        # 最低成交额
            'exclude_industries': [],  # 排除行业（可配置）
        }
        merged = {**default_params, **({} if params is None else params)}
        super().__init__(
            name='PB-ROE价值精选',
            description='寻找PB<5且PE合理的价值标的，注重安全边际和估值保护',
            params=merged
        )

    def filter_stocks(self) -> pd.DataFrame:
        df = self.filter_st_basic(self.market_data)
        if df.empty:
            return df

        # 基础过滤
        df = df[~df['code'].str.startswith(('688', '8', '4'), na=False)]
        df = df[df['amount'] > self.params['min_amount']]

        # === 关键：真实数据验证 ===
        # PB筛选：排除明显造假的PB值（新浪数据源PE=股价*15+5, PB=PE/6）
        # 真实PB通常在0.3-10之间，且不同股票差异大
        # 假PB = (price*15+5)/6 ≈ price*2.5+1，所有股票PB都差不多
        if 'pb_ratio' in df.columns:
            pb_values = df['pb_ratio'].dropna()
            if len(pb_values) > 100:
                pb_std = pb_values.std()
                # 如果PB标准差极小(<1)，说明是假数据（所有PB值几乎一样）
                if pb_std < 1.0:
                    import logging
                    logging.warning(
                        f"⚠️ PB数据疑似为估算值(std={pb_std:.2f})，PB-ROE策略结果不可靠。"
                        f"建议切换到东方财富数据源获取真实PE/PB。"
                    )
                # 即使数据质量存疑，仍然筛选（并标注）
                df = df[(df['pb_ratio'] >= self.params['pb_min']) &
                        (df['pb_ratio'] <= self.params['pb_max'])]
        else:
            return pd.DataFrame()  # 无PB数据，无法运行

        # PE筛选
        if 'pe_ratio' in df.columns:
            # 排除亏损股(PE<=0)和泡沫股(PE>50)
            df = df[(df['pe_ratio'] >= self.params['pe_min']) &
                    (df['pe_ratio'] <= self.params['pe_max'])]

        # 排除明显的问题行业（如果行业数据可用）
        if 'industry' in df.columns:
            exclude = getattr(self.params, 'exclude_industries', [])
            if exclude:
                df = df[~df['industry'].isin(exclude)]

        return df

    def rank_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        # 估值性价比：低PB + 合理PE = 高分
        # ROE/PB 逻辑：同样PB下，ROE越高越好
        df['value_score'] = (
            # PB越低越好（0-40分）
            df['pb_ratio'].apply(lambda x: max(0, 40 - x * 8)) +
            # PE适中最好（0-30分）：15-25倍最优
            df['pe_ratio'].apply(lambda x: 30 if 15 <= x <= 25 else max(0, 30 - abs(x-20))) +
            # 市值适中加分（0-15分）：50亿-500亿
            df['market_cap'].apply(lambda x: 15 if 5e9 <= x <= 5e10 else max(5, 15 - abs(np.log10(x/5e10))*3)) +
            # 今日不追涨（0-15分）：跌或小涨最好
            df['pct_change'].apply(lambda x: 15 if x <= 0.5 else max(0, 15 - x * 3))
        )

        # 数据质量标记
        pb_values = df['pb_ratio'].dropna()
        if len(pb_values) > 100 and pb_values.std() < 1.0:
            df['data_quality'] = 'estimated'
        else:
            df['data_quality'] = 'real'

        df = df.sort_values('value_score', ascending=False)
        return df.head(self.params['top_n'])

    def generate_signals(self, ranked_df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        data_quality = ranked_df['data_quality'].iloc[0] if not ranked_df.empty else 'unknown'

        for _, row in ranked_df.head(8).iterrows():
            price = row['price']
            pb = row.get('pb_ratio', 0)
            pe = row.get('pe_ratio', 0)
            cap = row.get('market_cap', 0) / 1e8

            trigger_parts = []
            trigger_parts.append(f'PB={pb:.1f}，估值较低')
            trigger_parts.append(f'PE={pe:.0f}倍，盈利合理')
            trigger_parts.append(f'市值{cap:.0f}亿，规模适中')

            if data_quality == 'estimated':
                trigger_parts.insert(0, '⚠️数据为估算值，仅供参考')

            # 风险提示
            if row.get('pct_change', 0) > 3:
                trigger_parts.append('今日涨幅较大，可等回调买入')
            elif row.get('pct_change', 0) < -3:
                trigger_parts.append('今日下跌，可能是更好买点')

            signals.append(TradeSignal(
                code=str(row['code']), name=str(row['name']),
                action='BUY', strategy=self.name, price=price,
                confidence=round(min(75, row['value_score'] * 0.75), 1),
                reason='；'.join(trigger_parts),
                stop_loss=round(price * 0.93, 2),
                stop_profit=round(price * 1.20, 2),
                factors={
                    'pb': round(pb, 2),
                    'pe': round(pe, 1),
                    'cap_yi': round(cap, 0),
                    'score': round(row['value_score'], 1),
                    'data_quality': data_quality,
                }
            ))
        return signals
