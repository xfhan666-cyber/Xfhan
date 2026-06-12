"""
策略基类 - 所有量化策略的抽象基类
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional
import pandas as pd


@dataclass
class TradeSignal:
    """交易信号"""
    code: str
    name: str
    action: str           # 'BUY' or 'SELL'
    strategy: str         # 策略名称
    price: float          # 建议价格
    confidence: float     # 置信度 0-100
    reason: str           # 推荐理由
    stop_loss: float = 0  # 止损价
    stop_profit: float = 0  # 止盈价
    timestamp: str = field(default_factory=lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    factors: Dict = field(default_factory=dict)  # 策略因子得分详情


@dataclass
class StrategyResult:
    """策略运行结果"""
    strategy_name: str
    signals: List[TradeSignal] = field(default_factory=list)
    selected_stocks: pd.DataFrame = field(default_factory=pd.DataFrame)
    summary: str = ''


class BaseStrategy(ABC):
    """策略基类"""

    def __init__(self, name: str, description: str, params: dict = None):
        self.name = name
        self.description = description
        self.params = params or {}
        self.market_data: Optional[pd.DataFrame] = None  # 全市场实时数据
        self.history_data: Dict[str, pd.DataFrame] = {}  # 历史K线缓存

    def set_market_data(self, df: pd.DataFrame):
        """设置全市场实时行情数据"""
        self.market_data = df

    def set_history_data(self, data: Dict[str, pd.DataFrame]):
        """设置历史K线数据"""
        self.history_data = data

    @abstractmethod
    def filter_stocks(self) -> pd.DataFrame:
        """筛选股票 - 子类必须实现"""
        pass

    @abstractmethod
    def rank_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        """对筛选后的股票打分排名 - 子类必须实现"""
        pass

    @abstractmethod
    def generate_signals(self, ranked_df: pd.DataFrame) -> List[TradeSignal]:
        """生成交易信号 - 子类必须实现"""
        pass

    def run(self) -> StrategyResult:
        """运行策略完整流程"""
        # 1. 筛选
        filtered = self.filter_stocks()
        if filtered.empty:
            return StrategyResult(strategy_name=self.name, summary='无符合条件的股票')

        # 2. 排名
        ranked = self.rank_stocks(filtered)

        # 3. 生成信号
        signals = self.generate_signals(ranked)

        # 4. 生成摘要
        top_n = min(5, len(ranked))
        top_stocks = ranked.head(top_n)[['code', 'name', 'score']].to_dict('records') if 'score' in ranked.columns else []

        summary = f"【{self.name}】共筛选出 {len(ranked)} 只股票，生成 {len(signals)} 个交易信号\n"
        if top_stocks:
            summary += f"Top{top_n} 股票: "
            summary += ', '.join([f"{s['name']}({s['code']}) 得分:{s.get('score', 'N/A')}" for s in top_stocks])

        return StrategyResult(
            strategy_name=self.name,
            signals=signals,
            selected_stocks=ranked,
            summary=summary
        )

    def filter_st_basic(self, df: pd.DataFrame) -> pd.DataFrame:
        """基础过滤：排除ST、涨停、跌停、停牌"""
        if df is None or df.empty:
            return pd.DataFrame()
        cond = (
            (~df['name'].str.contains('ST|\\*ST|退', na=False)) &
            (df['pct_change'].between(-9.5, 9.5)) &
            (df['price'] > 0) &
            (df['volume'] > 0)
        )
        return df[cond].copy()

    def calculate_moving_average(self, df: pd.DataFrame, periods: List[int]) -> pd.DataFrame:
        """计算移动平均线"""
        for p in periods:
            df[f'ma_{p}'] = df['close'].rolling(window=p).mean()
        return df

    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """计算RSI"""
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_bollinger(self, df: pd.DataFrame, period: int = 20, std: int = 2) -> pd.DataFrame:
        """计算布林带"""
        df['bb_mid'] = df['close'].rolling(window=period).mean()
        bb_std = df['close'].rolling(window=period).std()
        df['bb_upper'] = df['bb_mid'] + std * bb_std
        df['bb_lower'] = df['bb_mid'] - std * bb_std
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        return df

    def detect_candle_pattern(self, df: pd.DataFrame) -> pd.DataFrame:
        """检测K线形态"""
        # 锤子线
        body = abs(df['close'] - df['open'])
        lower_shadow = df['open'].combine(df['close'], min) - df['low']
        upper_shadow = df['high'] - df['open'].combine(df['close'], max)
        df['is_hammer'] = (lower_shadow > 2 * body) & (upper_shadow < body * 0.5) & (body > 0)
        # 启明星（简化版）
        df['is_morning_star'] = False
        return df
