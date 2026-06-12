"""
策略1：多因子综合打分模型
基于7个因子的行业中性化百分位打分，覆盖基本面+技术面
"""
import numpy as np
import pandas as pd
from typing import List
from strategies.base_strategy import BaseStrategy, TradeSignal, StrategyResult


class MultiFactorStrategy(BaseStrategy):
    def __init__(self, params: dict = None):
        default_params = {
            'top_n': 30,
            'weights': {
                'pe': 0.25, 'pb': 0.15, 'roe': 0.20,
                'growth': 0.15, 'momentum': 0.10,
                'turnover': 0.10, 'volatility': 0.05
            }
        }
        merged = {**default_params, **({} if params is None else params)}
        super().__init__(
            name='多因子综合打分',
            description='PE+PB+ROE+营收增速+动量+换手率+波动率，行业中性化百分位打分',
            params=merged
        )

    def filter_stocks(self) -> pd.DataFrame:
        df = self.filter_st_basic(self.market_data)
        if df.empty:
            return df
        # 排除北交所（流动性差）
        df = df[~df['code'].str.startswith('8', na=False)]
        # 排除市值<20亿
        df = df[df['market_cap'] > 2e9]
        # 排除日成交<2000万
        df = df[df['amount'] > 2e7]
        return df

    def rank_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        scores = pd.DataFrame(index=df.index)
        scores['code'] = df['code']
        scores['name'] = df['name']
        industry_col = 'industry' if 'industry' in df.columns else None

        def industry_percentile(series, industry, ascending=True):
            """行业中性化百分位排名"""
            if industry_col and industry_col in df.columns:
                result = pd.Series(0.0, index=df.index)
                for ind in df[industry_col].unique():
                    mask = df[industry_col] == ind
                    group_vals = series[mask].dropna()
                    if len(group_vals) > 1:
                        result[mask] = group_vals.rank(ascending=ascending, pct=True) * 100
                    else:
                        result[mask] = 50
                return result
            else:
                return series.dropna().rank(ascending=ascending, pct=True) * 100

        # PE得分：PE越低越好（但排除负PE）
        pe_clean = df['pe_ratio'].copy()
        pe_clean[pe_clean <= 0] = np.nan
        scores['pe_score'] = industry_percentile(pe_clean, df['industry'] if industry_col else None, ascending=True)

        # PB得分
        pb_clean = df['pb_ratio'].copy()
        pb_clean[pb_clean <= 0] = np.nan
        scores['pb_score'] = industry_percentile(pb_clean, df['industry'] if industry_col else None, ascending=True)

        # ROE得分：需要财务数据
        if 'roe' in df.columns:
            scores['roe_score'] = industry_percentile(df['roe'], df['industry'] if industry_col else None, ascending=False)
        else:
            scores['roe_score'] = 50

        # 增长得分：用YTD涨跌幅代理
        if 'pct_ytd' in df.columns:
            scores['growth_score'] = df['pct_ytd'].rank(pct=True) * 100
        else:
            scores['growth_score'] = 50

        # 动量得分：60日涨跌幅
        if 'pct_60d' in df.columns:
            scores['momentum_score'] = df['pct_60d'].rank(pct=True) * 100
        else:
            scores['momentum_score'] = 50

        # 换手率得分：适中最好
        if 'turnover' in df.columns:
            turnover_dev = abs(df['turnover'] - df['turnover'].median())
            scores['turnover_score'] = turnover_dev.rank(ascending=True, pct=True) * 100
        else:
            scores['turnover_score'] = 50

        # 波动率得分：低波动得分高（用振幅代理）
        if 'amplitude' in df.columns:
            scores['volatility_score'] = df['amplitude'].rank(ascending=True, pct=True) * 100
        else:
            scores['volatility_score'] = 50

        # 加权总分
        w = self.params['weights']
        scores['score'] = (
            scores['pe_score'].fillna(50) * w['pe'] +
            scores['pb_score'].fillna(50) * w['pb'] +
            scores['roe_score'].fillna(50) * w['roe'] +
            scores['growth_score'].fillna(50) * w['growth'] +
            scores['momentum_score'].fillna(50) * w['momentum'] +
            scores['turnover_score'].fillna(50) * w['turnover'] +
            scores['volatility_score'].fillna(50) * w['volatility']
        )

        result = df.copy()
        result['score'] = scores['score']
        result = result.sort_values('score', ascending=False)
        return result.head(self.params['top_n'])

    def generate_signals(self, ranked_df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        top_stocks = ranked_df.head(10)
        for _, row in top_stocks.iterrows():
            score = row.get('score', 0)
            confidence = min(95, score * 0.9)
            price = row.get('price', 0)
            signals.append(TradeSignal(
                code=str(row['code']),
                name=str(row['name']),
                action='BUY',
                strategy=self.name,
                price=price,
                confidence=round(confidence, 1),
                reason=f"综合得分{score:.1f}分，多因子排名Top{self.params['top_n']}。" +
                       f"PE={row.get('pe_ratio','N/A')}, PB={row.get('pb_ratio','N/A')}，行业中性化评分优异",
                stop_loss=round(price * 0.92, 2),
                stop_profit=round(price * 1.20, 2),
                factors={'score': round(score, 1)}
            ))
        return signals
