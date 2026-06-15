"""
板块轮动识别 — A股每年都有主线，找到主线就成功了一半

核心理念：
- A股是板块轮动市：每年1-2个主线板块贡献大部分涨幅
- 资金永远流向阻力最小的方向
- AI/科技/新能源/消费/医药...每年都有主升浪

输出：
- 今日最强板块Top10
- 主线板块（连续N日强势）
- 板块资金流向
- 板块内的优质标的
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SectorInfo:
    """板块信息"""
    name: str
    pct_change: float               # 板块涨幅(%)
    leading_stock: str = ''          # 领涨股
    limit_up_count: int = 0          # 板块内涨停数
    total_stocks: int = 0            # 板块股票总数
    amount: float = 0                # 板块成交额(亿)
    net_flow: float = 0              # 主力净流入(亿)
    consecutive_days: int = 0        # 连续强势天数
    is_main_theme: bool = False      # 是否主线板块
    ai_related: bool = False         # 是否AI/科技相关
    policy_related: bool = False     # 是否有政策催化


@dataclass
class SectorAnalysis:
    """板块轮动分析结果"""
    date: str = ''
    market_regime: str = ''
    top_sectors: List[SectorInfo] = field(default_factory=list)
    main_themes: List[SectorInfo] = field(default_factory=list)    # 主线板块
    ai_tech_sectors: List[SectorInfo] = field(default_factory=list) # AI/科技板块
    hot_stocks: List[str] = field(default_factory=list)            # 主线板块内的活跃股
    advice: List[str] = field(default_factory=list)


class SectorRotationAnalyzer:
    """
    板块轮动分析器

    识别逻辑：
    1. 板块涨幅排名（当日+近5日）
    2. 板块内涨停数（板块效应确认）
    3. 资金净流入（持续性验证）
    4. AI/科技/政策关键词匹配
    """

    # AI/科技相关关键词（板块名匹配）
    AI_TECH_KEYWORDS = [
        'AI', '人工智能', '算力', '芯片', '半导体', '光模块', 'CPO',
        '机器人', '自动驾驶', '数据', '云计算', '大模型', '软件',
        '通信', '5G', '6G', '量子', '服务器', '存储', 'PCB',
        '消费电子', '智能', '数字经济', '信创', '华为',
        '新能源', '光伏', '锂电', '储能', '电力', '充电',
        '低空经济', '商业航天', '卫星', '军工',
    ]

    def __init__(self):
        self._sector_history: Dict[str, List[float]] = {}  # 板块近期表现记录

    def analyze(self, market_df: pd.DataFrame,
                index_data: pd.DataFrame = None) -> SectorAnalysis:
        """
        从全市场数据中识别板块轮动

        由于AKShare板块接口可能不稳定，采用两种模式：
        1. 如果有行业字段 → 按行业统计
        2. 如果无行业字段 → 按概念/板块接口获取
        """
        result = SectorAnalysis(date=datetime.now().strftime('%Y-%m-%d'))

        # === 方案A：用market_df中的行业字段 ===
        if 'industry' in market_df.columns and (market_df['industry'] != '未知').sum() > 100:
            result = self._analyze_from_industry(market_df)
        else:
            # === 方案B：通过AKShare板块接口 ===
            result = self._analyze_from_sector_api()

        # === 识别AI/科技板块 ===
        result.ai_tech_sectors = [
            s for s in result.top_sectors
            if self._is_ai_tech(s.name)
        ]
        if result.ai_tech_sectors:
            result.advice.append(
                f"当前AI/科技主线活跃: {', '.join(s.name for s in result.ai_tech_sectors[:5])}"
            )

        # === 识别主线板块 ===
        result.main_themes = [
            s for s in result.top_sectors
            if s.limit_up_count >= 3 or s.consecutive_days >= 2
        ]
        if result.main_themes:
            result.advice.append(
                f"主线板块: {', '.join(s.name for s in result.main_themes[:5])}"
            )
        else:
            result.advice.append("当前无明显主线板块，宜多看少动")

        return result

    def _analyze_from_industry(self, df: pd.DataFrame) -> SectorAnalysis:
        """从行业字段分析板块轮动"""
        result = SectorAnalysis(date=datetime.now().strftime('%Y-%m-%d'))

        # 按行业聚合
        industry_groups = df.groupby('industry')

        sectors = []
        for ind, group in industry_groups:
            if ind == '未知' or len(group) < 3:
                continue

            avg_pct = group['pct_change'].mean()
            limit_ups = len(group[group['pct_change'] >= 9.8])
            total_amount = group['amount'].sum() / 1e8 if 'amount' in group.columns else 0

            # 找领涨股
            if not group.empty and 'pct_change' in group.columns:
                leader = group.loc[group['pct_change'].idxmax()]
                leader_name = f"{leader.get('name', '')}({leader.get('code', '')})"
            else:
                leader_name = ''

            # 计算连续强势天数
            consecutive = self._get_consecutive_days(ind, avg_pct)

            sectors.append(SectorInfo(
                name=ind,
                pct_change=round(avg_pct, 2),
                leading_stock=leader_name,
                limit_up_count=limit_ups,
                total_stocks=len(group),
                amount=round(total_amount, 0),
                consecutive_days=consecutive,
                is_main_theme=(limit_ups >= 3 or consecutive >= 2),
                ai_related=self._is_ai_tech(ind),
            ))

        # 按涨幅排序
        sectors.sort(key=lambda x: x.pct_change, reverse=True)
        result.top_sectors = sectors[:15]

        # 收集主线板块内的活跃股
        main_theme_names = {s.name for s in sectors if s.is_main_theme}
        if main_theme_names:
            theme_stocks = df[df['industry'].isin(main_theme_names)]
            # 涨幅>3%且在主线板块内
            hot = theme_stocks[theme_stocks['pct_change'] > 3]
            result.hot_stocks = hot['code'].tolist()[:30] if not hot.empty else []

        return result

    def _analyze_from_sector_api(self) -> SectorAnalysis:
        """通过AKShare板块接口获取板块数据"""
        result = SectorAnalysis(date=datetime.now().strftime('%Y-%m-%d'))

        try:
            import akshare as ak

            # 获取行业板块行情
            df = ak.stock_board_industry_name_em()
            if df is None or df.empty:
                return result

            df = df.rename(columns={
                '板块名称': 'name', '涨幅': 'pct_change',
                '领涨股票': 'leader', '上涨家数': 'up_count',
            })

            # 按涨幅排名
            df = df.sort_values('pct_change', ascending=False) if 'pct_change' in df.columns else df

            for _, row in df.head(15).iterrows():
                name = row.get('name', row.get('板块名称', ''))
                pct = row.get('pct_change', row.get('涨幅', 0))
                leader = row.get('leader', row.get('领涨股票', ''))

                if not name:
                    continue

                consecutive = self._get_consecutive_days(name, float(pct) if pct else 0)

                sectors = SectorInfo(
                    name=str(name),
                    pct_change=round(float(pct), 2) if pct else 0,
                    leading_stock=str(leader) if leader else '',
                    limit_up_count=0,  # 板块接口不提供涨停数
                    total_stocks=0,
                    consecutive_days=consecutive,
                    is_main_theme=(consecutive >= 2),
                    ai_related=self._is_ai_tech(str(name)),
                )
                result.top_sectors.append(sectors)

            result.advice.append('板块数据来自东方财富行业板块接口')

        except Exception as e:
            logger.warning(f"板块接口获取失败: {e}")
            result.advice.append('板块数据暂时不可用，个股推荐不受影响')

        return result

    def _is_ai_tech(self, sector_name: str) -> bool:
        """判断板块是否AI/科技相关"""
        name_upper = sector_name.upper()
        for kw in self.AI_TECH_KEYWORDS:
            if kw.upper() in name_upper:
                return True
        return False

    def _get_consecutive_days(self, sector_name: str, current_pct: float) -> int:
        """追踪板块连续强势天数（简易版：当日涨幅>1%算强势）"""
        if sector_name not in self._sector_history:
            self._sector_history[sector_name] = []

        history = self._sector_history[sector_name]
        history.append(current_pct)

        # 只保留最近10天
        if len(history) > 10:
            history = history[-10:]
            self._sector_history[sector_name] = history

        # 计算连续>1%的天数
        consecutive = 0
        for pct in reversed(history):
            if pct > 1.0:
                consecutive += 1
            else:
                break
        return consecutive

    def get_sector_hot_stocks(self, market_df: pd.DataFrame,
                               sector_name: str,
                               top_n: int = 5) -> pd.DataFrame:
        """获取指定板块内的最强个股"""
        if 'industry' not in market_df.columns:
            return pd.DataFrame()

        sector_df = market_df[market_df['industry'] == sector_name].copy()
        if sector_df.empty:
            return pd.DataFrame()

        # 排除ST和北交所
        sector_df = sector_df[~sector_df['name'].str.contains('ST|\\*ST', na=False)]
        sector_df = sector_df[~sector_df['code'].str.startswith(('8', '4'), na=False)]

        # 按涨幅排序
        if 'pct_change' in sector_df.columns:
            sector_df = sector_df.sort_values('pct_change', ascending=False)

        return sector_df.head(top_n)


# 单例
sector_analyzer = SectorRotationAnalyzer()
