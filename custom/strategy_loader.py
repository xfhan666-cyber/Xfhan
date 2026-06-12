"""
自定义策略加载器 - 解析YAML配置，动态生成策略
"""
import yaml
import os
import pandas as pd
from typing import List, Dict
from datetime import datetime
from strategies.base_strategy import BaseStrategy, TradeSignal, StrategyResult


class CustomStrategy(BaseStrategy):
    """从YAML配置动态生成的策略"""

    def __init__(self, config: dict):
        self.config = config
        self.conditions = config.get('conditions', {})
        self.must_include = self.conditions.get('must_include', [])
        self.ranking_factors = self.conditions.get('ranking_factors', [])
        self.position_config = self.conditions.get('position', {})
        self.rebalance_config = self.conditions.get('rebalance', {})
        self.risk_control = self.conditions.get('risk_control', {})

        super().__init__(
            name=config.get('strategy_name', '自定义策略'),
            description=config.get('description', ''),
            params=config
        )

    def _check_condition(self, row: pd.Series, condition_str: str) -> bool:
        """解析并检查单条条件表达式"""
        try:
            # 支持的字段映射
            field_map = {
                'dividend_yield': 'dividend_yield',
                'daily_volume': 'amount',
                'pe_ratio': 'pe_ratio',
                'pb_ratio': 'pb_ratio',
                'roe': 'roe',
                'is_st': 'is_st',
                'market_cap': 'market_cap',
                'turnover': 'turnover',
                'pct_change': 'pct_change',
                'revenue_growth': 'revenue_growth',
                'volatility_60d': 'pct_60d',
                'pct_ytd': 'pct_ytd',
            }

            parts = condition_str.strip().split()
            if len(parts) < 3:
                return True

            field = field_map.get(parts[0], parts[0])
            op = parts[1]
            val = parts[2]

            if field not in row.index:
                return True

            actual = row[field]
            if isinstance(actual, bool):
                if op == '==' and val.lower() == 'false':
                    return not actual
                if op == '==' and val.lower() == 'true':
                    return actual
                return True

            if isinstance(actual, str):
                return True

            actual = float(actual) if pd.notna(actual) else 0
            val = float(val)

            if op == '>':
                return actual > val
            elif op == '<':
                return actual < val
            elif op == '>=':
                return actual >= val
            elif op == '<=':
                return actual <= val
            elif op == '==':
                return actual == val
            return True
        except Exception:
            return True

    def filter_stocks(self) -> pd.DataFrame:
        df = self.filter_st_basic(self.market_data)
        if df.empty:
            return df

        # 应用所有筛选条件
        for condition in self.must_include:
            mask = df.apply(lambda row: self._check_condition(row, condition), axis=1)
            df = df[mask]

        return df

    def rank_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or not self.ranking_factors:
            return df

        scores = pd.Series(0.0, index=df.index)

        for factor in self.ranking_factors:
            field = factor.get('field', '')
            weight = factor.get('weight', 0) / 100
            order = factor.get('order', 'desc')

            field_map = {
                'dividend_yield': 'dividend_yield',
                'daily_volume': 'amount',
                'pe_ratio': 'pe_ratio',
                'pb_ratio': 'pb_ratio',
                'roe': 'roe',
                'market_cap': 'market_cap',
                'turnover': 'turnover',
                'pct_change': 'pct_change',
                'volatility_60d': 'pct_60d',
                'pct_ytd': 'pct_ytd',
            }

            col = field_map.get(field, field)
            if col not in df.columns:
                continue

            ascending = order == 'asc'
            ranking = df[col].rank(ascending=ascending, pct=True) * 100
            scores += ranking.fillna(50) * weight

        result = df.copy()
        result['score'] = scores
        result = result.sort_values('score', ascending=False)

        max_stocks = self.position_config.get('max_stocks', 20)
        return result.head(max_stocks)

    def generate_signals(self, ranked_df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        stop_loss = self.risk_control.get('stop_loss_pct', 8)
        stop_profit = self.risk_control.get('stop_profit_pct', 20)

        for _, row in ranked_df.head(10).iterrows():
            price = row.get('price', 0)
            reasons = []
            if self.ranking_factors:
                top_factors = sorted(self.ranking_factors, key=lambda x: x.get('weight', 0), reverse=True)[:3]
                reasons.append('关注因子: ' + ', '.join([f['field'] for f in top_factors]))

            signals.append(TradeSignal(
                code=str(row['code']), name=str(row['name']),
                action='BUY', strategy=self.name, price=price,
                confidence=round(min(85, row.get('score', 50) * 0.8), 1),
                reason='; '.join(reasons) if reasons else f"自定义策略筛选，得分{row.get('score', 0):.1f}",
                stop_loss=round(price * (1 - stop_loss / 100), 2),
                stop_profit=round(price * (1 + stop_profit / 100), 2),
                factors={'score': round(row.get('score', 0), 1)}
            ))

        return signals


class StrategyLoader:
    """自定义策略加载器"""

    def __init__(self, strategies_dir: str = None):
        if strategies_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            strategies_dir = os.path.join(base, 'custom', 'user_strategies')
        self.strategies_dir = strategies_dir
        os.makedirs(strategies_dir, exist_ok=True)

    def list_strategies(self) -> List[dict]:
        """列出所有自定义策略"""
        strategies = []
        if not os.path.exists(self.strategies_dir):
            return strategies
        for f in os.listdir(self.strategies_dir):
            if f.endswith(('.yaml', '.yml')):
                path = os.path.join(self.strategies_dir, f)
                try:
                    with open(path, 'r', encoding='utf-8') as fp:
                        config = yaml.safe_load(fp)
                        strategies.append({
                            'filename': f,
                            'name': config.get('strategy_name', f),
                            'description': config.get('description', ''),
                            'path': path
                        })
                except Exception:
                    pass
        return strategies

    def load_strategy(self, filename: str) -> CustomStrategy:
        """加载单个策略文件"""
        path = os.path.join(self.strategies_dir, filename)
        with open(path, 'r', encoding='utf-8') as fp:
            config = yaml.safe_load(fp)
        return CustomStrategy(config)

    def load_all(self) -> List[CustomStrategy]:
        """加载所有自定义策略"""
        strategies = []
        for info in self.list_strategies():
            try:
                strategy = self.load_strategy(info['filename'])
                strategies.append(strategy)
            except Exception as e:
                print(f"加载 {info['filename']} 失败: {e}")
        return strategies

    def save_strategy(self, filename: str, yaml_content: str) -> bool:
        """保存策略配置"""
        path = os.path.join(self.strategies_dir, filename)
        try:
            with open(path, 'w', encoding='utf-8') as fp:
                fp.write(yaml_content)
            return True
        except Exception:
            return False

    def delete_strategy(self, filename: str) -> bool:
        """删除策略文件"""
        path = os.path.join(self.strategies_dir, filename)
        try:
            if os.path.exists(path):
                os.remove(path)
            return True
        except Exception:
            return False


# 单例
loader = StrategyLoader()
