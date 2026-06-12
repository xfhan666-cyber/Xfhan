"""
策略7：首板打板策略
用户自定义的涨停板首板战法 - 早盘封板+题材共振+量能确认+次日必卖
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime, time
from strategies.base_strategy import BaseStrategy, TradeSignal, StrategyResult


class FirstBoardStrategy(BaseStrategy):
    """
    首板打板策略

    核心理念：
    - 只做10:30前封板的首板（非一字板）
    - 同题材≥3只涨停确认板块效应
    - 流通市值30-80亿的活跃小票
    - 封单/成交额>20% + 量比≥3
    - 底部首板或平台突破形态
    - 次日必卖，严格止损
    """

    def __init__(self, params: dict = None):
        default_params = {
            # 选股条件
            'seal_deadline': '10:30',         # 封板截止时间
            'min_sector_stocks': 3,            # 同板块最少涨停数
            'float_cap_min': 30e8,             # 最小流通市值(30亿)
            'float_cap_max': 80e8,             # 最大流通市值(80亿)
            'seal_amount_ratio': 0.20,         # 封单/成交额最低比例
            'volume_ratio_min': 3.0,           # 最低量比
            'recent_limit_up_count': 2,        # 半年内最少涨停次数(股性)
            'recent_days': 120,               # 股性考察天数

            # 买入过滤
            'prefer_change_hand': True,        # 优先换手板
            'prefer_re_seal': True,            # 优先回封板
            're_seal_timeout': 5,              # 回封时间限制(分钟)

            # 卖出规则
            'high_open_threshold': 3.0,        # 高开阈值(%)
            'flat_open_range': 1.0,            # 平开范围(%)
            'low_open_stop': -2.0,             # 低开止损线(%)
            'force_sell_min': 10,              # 强制卖出时间(分钟)

            # 风控
            'single_stop_loss': -3.0,          # 单笔止损(%)
            'daily_stop_loss': -2.0,           # 单日总止损(%)
            'monthly_stop_loss': -10.0,        # 月度止损(%)

            # 仓位
            'portfolio_small': 2,              # 70万以下持仓数
            'portfolio_mid': 4,               # 70-500万持仓数
            'portfolio_large': 8,             # 500万以上持仓数

            # 排除
            'exclude_st': True,                # 排除ST
            'exclude_new_stock': True,          # 排除次新股(上市<60天)
            'exclude_high_position': True,      # 排除高位板(60日涨幅>50%)
            'exclude_yizi': True,              # 排除一字板

            'top_n': 10,
        }
        merged = {**default_params, **({} if params is None else params)}
        super().__init__(
            name='首板打板策略',
            description='早盘10:30前封板+题材共振(≥3只)+市值30-80亿+量比≥3+底部/突破形态，次日必卖',
            params=merged
        )

    def _is_morning_seal(self, row: pd.Series) -> bool:
        """判断是否早盘封板（简化：振幅<5%说明早盘封板）"""
        if 'amplitude' in row.index and pd.notna(row['amplitude']):
            return row['amplitude'] < 5.0
        return True

    def _is_yizi_board(self, row: pd.Series) -> bool:
        """判断是否一字板"""
        if 'open' in row.index and 'pre_close' in row.index:
            if pd.notna(row['open']) and pd.notna(row['pre_close']) and row['pre_close'] > 0:
                return row['open'] >= row['pre_close'] * 1.09
        return False

    def _is_high_position(self, row: pd.Series, history_data: Dict) -> bool:
        """判断是否高位（60日涨幅>50%）"""
        code = str(row['code'])
        if code in history_data:
            df_hist = history_data[code]
            if df_hist is not None and not df_hist.empty and len(df_hist) >= 60:
                close_60d_ago = df_hist['close'].iloc[-60]
                current = row.get('price', df_hist['close'].iloc[-1])
                if close_60d_ago > 0:
                    pct_60d = (current / close_60d_ago - 1) * 100
                    return pct_60d > 50
        # 用pct_60d字段判断
        if 'pct_60d' in row.index and pd.notna(row['pct_60d']):
            return row['pct_60d'] > 50
        return False

    def _is_bottom_or_breakout(self, row: pd.Series, history_data: Dict) -> bool:
        """判断底部首板或平台突破形态"""
        code = str(row['code'])
        if code not in history_data:
            return True  # 无历史数据时不排除

        df_hist = history_data[code]
        if df_hist is None or df_hist.empty or len(df_hist) < 60:
            return True

        close_prices = df_hist['close']
        current = row.get('price', close_prices.iloc[-1])

        # 底部判断：当前价在60日均线附近(<15%偏离)
        ma_60 = close_prices.tail(60).mean()
        deviation = (current / ma_60 - 1) * 100 if ma_60 > 0 else 0

        # 平台突破判断：近20日最高价被突破
        high_20 = close_prices.tail(20).max()
        is_breakout = current >= high_20 * 0.98

        # 底部或突破
        return deviation < 15 or is_breakout

    def _check_sector_consensus(self, df: pd.DataFrame, row: pd.Series) -> bool:
        """检查同板块是否有≥3只涨停（板块效应）"""
        if 'industry' not in df.columns or 'industry' not in row.index:
            return True  # 无行业数据时不排除

        industry = row['industry']
        if pd.isna(industry):
            return True

        same_sector = df[df['industry'] == industry]
        limit_up_count = len(same_sector[same_sector['pct_change'] >= 9.8])
        return limit_up_count >= self.params['min_sector_stocks']

    def filter_stocks(self) -> pd.DataFrame:
        df = self.filter_st_basic(self.market_data)
        if df.empty:
            return df

        # 1. 只保留今日涨停股
        df = df[df['pct_change'] >= 9.8].copy()
        if df.empty:
            return df

        # 2. 排除一字板
        if self.params['exclude_yizi']:
            df = df[~df.apply(lambda r: self._is_yizi_board(r), axis=1)]

        # 3. 早盘封板判断
        df = df[df.apply(lambda r: self._is_morning_seal(r), axis=1)]

        # 4. 流通市值 30-80亿
        if 'float_cap' in df.columns:
            df = df[df['float_cap'].between(self.params['float_cap_min'], self.params['float_cap_max'])]
        elif 'market_cap' in df.columns:
            # 用总市值近似（流通市值约60-80%总市值）
            df = df[df['market_cap'].between(40e8, 120e8)]

        # 5. 排除ST
        if self.params['exclude_st']:
            df = df[~df['name'].str.contains('ST|\\*ST|退', na=False)]

        # 6. 排除北交所
        df = df[~df['code'].str.startswith(('8', '4'), na=False)]

        # 7. 量比≥3
        if 'volume_ratio' in df.columns:
            df = df[df['volume_ratio'] >= self.params['volume_ratio_min']]

        return df

    def rank_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        scores = pd.DataFrame(index=df.index)
        scores['code'] = df['code']
        scores['name'] = df['name']

        # 1. 板块效应加分
        if 'industry' in df.columns:
            scores['sector_score'] = df.apply(
                lambda r: 100 if self._check_sector_consensus(df, r) else 30, axis=1)
        else:
            scores['sector_score'] = 50

        # 2. 形态加分：底部/突破
        scores['form_score'] = df.apply(
            lambda r: 100 if self._is_bottom_or_breakout(r, self.history_data) else 20, axis=1)

        # 3. 换手板加分（换手板特征：振幅>3%且<8%）
        if 'amplitude' in df.columns:
            scores['change_hand_score'] = df['amplitude'].apply(
                lambda x: 100 if 3 < x < 8 else (70 if x <= 3 else 30))
        else:
            scores['change_hand_score'] = 50

        # 4. 封单力度（用换手率代理：低换手=封单稳）
        if 'turnover' in df.columns:
            scores['seal_score'] = df['turnover'].apply(
                lambda x: 100 if x < 5 else (80 if x < 10 else 50))
        else:
            scores['seal_score'] = 50

        # 5. 高位排除扣分
        scores['position_score'] = df.apply(
            lambda r: 20 if self._is_high_position(r, self.history_data) else 100, axis=1)

        # 6. 量比越大越好（但不要过大>15）
        if 'volume_ratio' in df.columns:
            scores['volume_score'] = df['volume_ratio'].apply(
                lambda x: min(100, x / 10 * 100) if x < 15 else 60)
        else:
            scores['volume_score'] = 50

        # 综合得分（板块效应+形态权重最高）
        scores['score'] = (
            scores['sector_score'] * 0.30 +
            scores['form_score'] * 0.25 +
            scores['change_hand_score'] * 0.15 +
            scores['seal_score'] * 0.15 +
            scores['position_score'] * 0.10 +
            scores['volume_score'] * 0.05
        )

        result = df.copy()
        result['score'] = scores['score']
        result = result.sort_values('score', ascending=False)
        return result.head(self.params['top_n'])

    def generate_signals(self, ranked_df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        for _, row in ranked_df.head(8).iterrows():
            price = row['price']
            cap = row.get('market_cap', row.get('float_cap', 0)) / 1e8

            # 构建详细推荐理由
            reasons = []
            reasons.append(f"流通市值{cap:.0f}亿，早盘封板")

            if 'industry' in row.index and pd.notna(row['industry']):
                sector_count = len(self.market_data[
                    (self.market_data['industry'] == row['industry']) &
                    (self.market_data['pct_change'] >= 9.8)
                ]) if 'industry' in self.market_data.columns else 0
                if sector_count >= self.params['min_sector_stocks']:
                    reasons.append(f"板块{row['industry']}共振({sector_count}只涨停)")
                else:
                    reasons.append(f"板块效应不足({sector_count}/{self.params['min_sector_stocks']})")

            if 'volume_ratio' in row.index and pd.notna(row['volume_ratio']):
                reasons.append(f"量比{row['volume_ratio']:.1f}倍")

            if 'amplitude' in row.index:
                amp = row['amplitude']
                if 3 < amp < 8:
                    reasons.append("换手板(拉升后横盘封板)")
                elif amp <= 3:
                    reasons.append("早盘强势秒板")
                else:
                    reasons.append("烂板回封")

            # 形态判断
            if self._is_bottom_or_breakout(row, self.history_data):
                reasons.append("底部/平台突破形态")
            if self._is_high_position(row, self.history_data):
                reasons.append("⚠️高位板(谨慎)")

            signals.append(TradeSignal(
                code=str(row['code']),
                name=str(row['name']),
                action='BUY',
                strategy=self.name,
                price=price,
                confidence=round(min(88, row.get('score', 50) * 0.85), 1),
                reason='; '.join(reasons),
                stop_loss=round(price * (1 + self.params['single_stop_loss'] / 100), 2),  # 次日低开>2%止损
                stop_profit=round(price * 1.05, 2),  # 次日溢价5%
                factors={
                    'score': round(row.get('score', 0), 1),
                    'cap': f'{cap:.0f}亿',
                    'volume_ratio': round(row.get('volume_ratio', 0), 1) if 'volume_ratio' in row.index else 0
                }
            ))

        return signals

    def get_sell_advice(self, signal: TradeSignal, next_day_open: float,
                         next_day_high: float, next_day_low: float) -> dict:
        """
        次日卖出建议（根据用户规则）
        返回: {action, reason, sell_pct}
        """
        entry_price = signal.price
        open_pct = (next_day_open / entry_price - 1) * 100

        if open_pct >= self.params['high_open_threshold']:
            return {
                'action': 'SELL_SPLIT',
                'reason': f'高开{open_pct:.1f}%≥3%，竞价卖50%，10分钟不强势清仓',
                'sell_pct': 50,
                'conditional': True,
                'condition': f'10分钟内涨幅<{open_pct + 1}%则清仓'
            }
        elif abs(open_pct) <= self.params['flat_open_range']:
            return {
                'action': 'SELL_IF_WEAK',
                'reason': f'平开{open_pct:+.1f}%，9:40前冲高无力就走',
                'sell_pct': 100,
                'conditional': True,
                'condition': '9:40前涨幅<1%则全卖'
            }
        elif open_pct <= self.params['low_open_stop']:
            return {
                'action': 'STOP_LOSS',
                'reason': f'低开{open_pct:.1f}%{open_pct:<}-2%，开盘3分钟内止损',
                'sell_pct': 100,
                'conditional': False
            }
        else:
            return {
                'action': 'SELL_IF_NOT_RED',
                'reason': f'低开{open_pct:.1f}%在2%内，15分钟不翻红清仓',
                'sell_pct': 100,
                'conditional': True,
                'condition': '15分钟内不翻红则全卖'
            }
