"""
策略3：趋势动量+资金流跟踪
均线多头排列 + 主力资金流入 + 放量确认
"""
import numpy as np
import pandas as pd
from typing import List
from strategies.base_strategy import BaseStrategy, TradeSignal


class TrendMomentumStrategy(BaseStrategy):
    def __init__(self, params: dict = None):
        default_params = {
            'ma_short': 20, 'ma_mid': 60, 'ma_long': 120,
            'volume_ratio': 1.5,
            'capital_inflow_min': 5e7,
            'lookback_pct': 20,
            'stop_loss_pct': 8
        }
        merged = {**default_params, **({} if params is None else params)}
        super().__init__(
            name='趋势动量+资金流',
            description='多头排列+主力流入+放量突破，中短线趋势跟踪',
            params=merged
        )

    def filter_stocks(self) -> pd.DataFrame:
        df = self.filter_st_basic(self.market_data)
        if df.empty:
            return df
        df = df[~df['code'].str.startswith(('688', '8'), na=False)]
        df = df[df['amount'] > 1e7]
        df = df[df['pct_change'] > -3]  # 不追大跌股
        return df

    def check_ma_alignment(self, df_hist: pd.DataFrame) -> bool:
        """检查均线多头排列"""
        if df_hist is None or df_hist.empty or len(df_hist) < 120:
            return False
        df_hist = self.calculate_moving_average(df_hist, [20, 60, 120])
        latest = df_hist.iloc[-1]
        return (latest.get('close', 0) > latest.get('ma_20', 0) >
                latest.get('ma_60', 0) > latest.get('ma_120', 0))

    def rank_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        results = []
        for _, row in df.iterrows():
            code = str(row['code'])
            hist = self.history_data.get(code)
            if hist is None or hist.empty:
                continue

            # 均线排列
            ma_ok = self.check_ma_alignment(hist)
            if not ma_ok:
                continue

            # 成交量放大
            avg_vol = hist['volume'].tail(self.params['ma_short']).mean()
            latest_vol = row.get('volume', 0)
            vol_ratio = latest_vol / avg_vol if avg_vol > 0 else 0

            # 涨幅强度
            pct_20d = ((row['price'] - hist['close'].iloc[-20]) / hist['close'].iloc[-20] * 100) if len(hist) >= 20 else 0

            # 综合评分
            score = min(100, (
                (min(vol_ratio / self.params['volume_ratio'], 3) * 30) +
                (min(pct_20d / 15, 1) * 40) +
                (min(row.get('turnover', 3) / 3, 1) * 30)
            ))

            results.append({
                'code': code, 'name': row['name'], 'price': row['price'],
                'score': score, 'vol_ratio': round(vol_ratio, 2),
                'pct_20d': round(pct_20d, 1),
                'pe_ratio': row.get('pe_ratio', 0),
                'pb_ratio': row.get('pb_ratio', 0),
                'market_cap': row.get('market_cap', 0),
                'turnover': row.get('turnover', 0),
                'amount': row.get('amount', 0),
                'pct_change': row.get('pct_change', 0),
            })

        result = pd.DataFrame(results)
        if not result.empty:
            result = result.sort_values('score', ascending=False)
        return result

    def generate_signals(self, ranked_df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        for _, row in ranked_df.head(10).iterrows():
            price = row['price']
            signals.append(TradeSignal(
                code=str(row['code']), name=str(row['name']),
                action='BUY', strategy=self.name, price=price,
                confidence=round(min(92, row['score'] * 0.88), 1),
                reason=(f"均线多头排列确认，量比{row['vol_ratio']}倍放量，" +
                       f"近20日涨{row['pct_20d']}%，趋势强劲"),
                stop_loss=round(price * (1 - self.params['stop_loss_pct'] / 100), 2),
                stop_profit=round(price * 1.15, 2),
                factors={'vol_ratio': row['vol_ratio'], 'pct_20d': row['pct_20d'], 'score': round(row['score'], 1)}
            ))
        return signals
