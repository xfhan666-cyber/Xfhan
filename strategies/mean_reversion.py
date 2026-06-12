"""
策略4：反转因子+超跌反弹
严重超跌后缩量止跌的反弹机会
"""
import numpy as np
import pandas as pd
from typing import List
from strategies.base_strategy import BaseStrategy, TradeSignal


class MeanReversionStrategy(BaseStrategy):
    def __init__(self, params: dict = None):
        default_params = {
            'decline_pct': 10,
            'turnover_max': 1,
            'stop_profit_pct': 5,
            'stop_loss_pct': 3,
            'max_hold_days': 10
        }
        merged = {**default_params, **({} if params is None else params)}
        super().__init__(
            name='超跌反弹',
            description='近20日跌幅前10%+缩量止跌+底部形态，短期反转博弈',
            params=merged
        )

    def filter_stocks(self) -> pd.DataFrame:
        df = self.filter_st_basic(self.market_data)
        if df.empty:
            return df
        df = df[~df['code'].str.startswith(('688', '8'), na=False)]
        df = df[df['amount'] > 5e6]
        df = df[df['market_cap'] > 3e9]
        return df

    def rank_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        results = []
        for _, row in df.iterrows():
            code = str(row['code'])
            hist = self.history_data.get(code)
            if hist is None or hist.empty or len(hist) < 20:
                continue

            close_prices = hist['close']
            pct_20d = ((row['price'] - close_prices.iloc[-20]) / close_prices.iloc[-20] * 100)

            # 必须超跌
            if pct_20d > -self.params['decline_pct']:
                continue

            # 缩量
            current_vol = row.get('volume', 0)
            avg_vol_20 = hist['volume'].tail(20).mean()
            vol_ratio = current_vol / avg_vol_20 if avg_vol_20 > 0 else 1

            # PE合理性（排除亏损股）
            pe = row.get('pe_ratio', 0)

            # 偏离均线程度
            ma_20 = close_prices.tail(20).mean()
            deviation = (row['price'] - ma_20) / ma_20 * 100

            # 跌幅越深+缩量越好+PE合理 = 高分
            score = min(100, (
                min(abs(pct_20d) / self.params['decline_pct'], 2) * 40 +
                max(0, (1 - vol_ratio + 0.1)) * 30 +
                (15 if 0 < pe < 50 else 5) +
                max(0, 15 - abs(deviation + 10) * 0.5)
            ))

            results.append({
                'code': code, 'name': row['name'], 'price': row['price'],
                'score': score, 'pct_20d': round(pct_20d, 1),
                'vol_ratio': round(vol_ratio, 2),
                'pe_ratio': pe, 'pb_ratio': row.get('pb_ratio', 0),
                'deviation': round(deviation, 1),
                'turnover': row.get('turnover', 0),
                'amount': row.get('amount', 0),
                'pct_change': row.get('pct_change', 0),
            })

        result = pd.DataFrame(results)
        if not result.empty:
            result = result.sort_values('score', ascending=False)
        return result.head(20)

    def generate_signals(self, ranked_df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        for _, row in ranked_df.head(8).iterrows():
            price = row['price']
            signals.append(TradeSignal(
                code=str(row['code']), name=str(row['name']),
                action='BUY', strategy=self.name, price=price,
                confidence=round(min(80, row['score'] * 0.8), 1),
                reason=(f"近20日跌{abs(row['pct_20d'])}%，量比{row['vol_ratio']}缩量止跌，" +
                       f"偏离均线{row['deviation']}%，超跌反弹机会。短线操作，快进快出"),
                stop_loss=round(price * (1 - self.params['stop_loss_pct'] / 100), 2),
                stop_profit=round(price * (1 + self.params['stop_profit_pct'] / 100), 2),
                factors={'pct_20d': row['pct_20d'], 'vol_ratio': row['vol_ratio'], 'score': round(row['score'], 1)}
            ))
        return signals
