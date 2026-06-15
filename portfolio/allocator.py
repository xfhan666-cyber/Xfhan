"""
投资组合分配器 - 解决"推荐太多，资金有限"的问题
根据总资金、风险偏好、策略信号，输出最优买入组合和具体数量
"""
import math
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from strategies.base_strategy import TradeSignal


@dataclass
class AllocationResult:
    """分配结果"""
    stock: TradeSignal
    shares: int                    # 建议买入股数（整手=100股）
    amount: float                  # 建议买入金额
    weight: float                  # 占总资金比例(%)
    reason: str                    # 分配理由


@dataclass
class PortfolioPlan:
    """组合计划"""
    total_capital: float = 100000   # 总资金
    used_capital: float = 0         # 已用资金
    cash_reserved: float = 0        # 预留现金
    allocations: List[AllocationResult] = field(default_factory=list)
    risk_score: float = 0           # 组合风险评分
    expected_return: float = 0      # 预期收益
    notes: List[str] = field(default_factory=list)


class PortfolioAllocator:
    """
    投资组合分配器

    核心理念：
    - 每天最多买2-4只，资金分散
    - 单票仓位上限15%，同行业上限30%
    - 预留20%现金应对T+1无法卖出时的机会
    - 优先高置信度+多策略共识的标的
    """

    def __init__(self, total_capital: float = 100000):
        """
        Args:
            total_capital: 总资金（元）
        """
        self.total_capital = total_capital
        self.max_single_position = 0.15     # 单票最大仓位
        self.max_industry_exposure = 0.30    # 单行业最大暴露
        self.cash_reserve_ratio = 0.20       # 预留现金比例
        self.max_positions = 4               # 最大持仓数
        self.min_position = 0.05             # 最小仓位
        self.lot_size = 100                  # A股1手=100股

    def allocate(self, signals: List[TradeSignal],
                 risk_level: str = 'moderate') -> PortfolioPlan:
        """
        根据信号列表生成最优投资组合

        Args:
            signals: 策略产生的买入信号列表
            risk_level: 'conservative' | 'moderate' | 'aggressive'

        Returns:
            PortfolioPlan 包含具体买入方案
        """
        plan = PortfolioPlan(total_capital=self.total_capital)

        if not signals:
            plan.notes.append("无可用信号，建议空仓等待")
            return plan

        # 1. 按风险偏好筛选
        if risk_level == 'conservative':
            # 保守：只要置信度≥75%的多策略共识信号
            filtered = [s for s in signals if s.confidence >= 75 and '|' in s.reason]
            max_positions = 2
            cash_ratio = 0.35
        elif risk_level == 'aggressive':
            # 激进：置信度≥55%即可
            filtered = [s for s in signals if s.confidence >= 55]
            max_positions = 4
            cash_ratio = 0.10
        else:
            # 稳健（默认）：置信度≥70%
            filtered = [s for s in signals if s.confidence >= 65]
            max_positions = 3
            cash_ratio = 0.20

        self.max_positions = max_positions
        self.cash_reserve_ratio = cash_ratio

        # 2. 按置信度排序，取Top N
        filtered.sort(key=lambda s: s.confidence, reverse=True)
        candidates = filtered[:max_positions * 2]  # 多取一些用于分散行业

        if not candidates:
            plan.notes.append(
                f"当前{risk_level}模式下无足够高置信度信号。"
                f"最高置信度: {signals[0].confidence:.0f}%（需要≥{65 if risk_level == 'moderate' else 75}%）"
            )
            return plan

        # 3. 行业分散（避免同行业过度集中）
        selected = self._diversify_by_industry(candidates, max_positions)

        if not selected:
            # 行业信息不足时退化为置信度排名
            selected = candidates[:max_positions]
            plan.notes.append("⚠️ 行业信息不完整，按置信度排名选取")

        # 4. 仓位分配（凯利公式变体 + 等风险预算）
        available = self.total_capital * (1 - self.cash_reserve_ratio)
        allocations = self._allocate_positions(selected, available, risk_level)

        # 5. 计算组合指标
        plan.allocations = allocations
        plan.used_capital = sum(a.amount for a in allocations)
        plan.cash_reserved = self.total_capital - plan.used_capital
        plan.risk_score = self._calc_portfolio_risk(allocations)
        plan.expected_return = self._calc_expected_return(allocations)

        return plan

    def _diversify_by_industry(self, candidates: List[TradeSignal],
                                max_picks: int) -> List[TradeSignal]:
        """按行业分散选择标的"""
        # 尝试从factors中获取行业信息
        industries = {}
        for s in candidates:
            ind = s.factors.get('industry', s.factors.get('sector', 'unknown'))
            if ind not in industries:
                industries[ind] = []
            industries[ind].append(s)

        selected = []
        industry_count = {}

        # 轮询每个行业取置信度最高的
        sorted_industries = sorted(
            industries.items(),
            key=lambda x: max(s.confidence for s in x[1]),
            reverse=True
        )

        for ind, stocks in sorted_industries:
            if len(selected) >= max_picks:
                break
            # 每个行业最多选2只
            for s in sorted(stocks, key=lambda x: x.confidence, reverse=True):
                if len(selected) >= max_picks:
                    break
                if industry_count.get(ind, 0) >= 2:
                    break
                selected.append(s)
                industry_count[ind] = industry_count.get(ind, 0) + 1

        return selected

    def _allocate_positions(self, stocks: List[TradeSignal],
                             available: float,
                             risk_level: str) -> List[AllocationResult]:
        """等风险预算分配仓位"""
        if not stocks:
            return []

        n = len(stocks)

        # 基础等权分配
        base_weight = min(1.0 / n, self.max_single_position)

        # 根据置信度调整权重
        confidences = [s.confidence for s in stocks]
        avg_conf = sum(confidences) / len(confidences) if confidences else 50

        # 置信度偏置：高置信度多分配
        conf_weights = []
        for conf in confidences:
            bias = 1.0 + (conf - avg_conf) / 200  # 偏离均值±25%
            conf_weights.append(max(0.5, min(1.5, bias)))

        # 归一化
        total_bias = sum(conf_weights)
        norm_weights = [w / total_bias for w in conf_weights]

        # 生成分配结果
        results = []
        for i, (stock, norm_w) in enumerate(zip(stocks, norm_weights)):
            weight = min(norm_w * 0.8, self.max_single_position)  # 避免超配
            amount = available * weight
            price = stock.price
            shares_raw = amount / price
            # 取整手(100股)
            lots = math.floor(shares_raw / self.lot_size)
            shares = lots * self.lot_size
            actual_amount = shares * price

            # 最少买1手
            if shares < self.lot_size:
                shares = self.lot_size
                actual_amount = shares * price

            # 检查是否超预算
            if actual_amount > available * self.max_single_position:
                shares = math.floor(available * self.max_single_position / price / self.lot_size) * self.lot_size
                actual_amount = shares * price

            results.append(AllocationResult(
                stock=stock,
                shares=shares,
                amount=round(actual_amount, 2),
                weight=round(actual_amount / self.total_capital * 100, 1),
                reason=self._allocation_reason(stock, risk_level)
            ))

        return results

    def _allocation_reason(self, signal: TradeSignal, risk_level: str) -> str:
        """生成分配理由"""
        parts = []
        if signal.confidence >= 80:
            parts.append("高置信度优先配置")
        elif signal.confidence >= 70:
            parts.append("中等置信度标准配置")
        else:
            parts.append("低置信度轻仓试探")

        if '|' in signal.reason:
            parts.append("多策略共识加分")

        if risk_level == 'conservative':
            parts.append("保守模式仓位受限")
        elif risk_level == 'aggressive':
            parts.append("激进模式允许较高仓位")

        return '; '.join(parts) if parts else '标准配置'

    def _calc_portfolio_risk(self, allocations: List[AllocationResult]) -> float:
        """估算组合风险（基于仓位集中度）"""
        if not allocations:
            return 0
        # Herfindahl指数：越高越集中
        weights = [a.weight / 100 for a in allocations]
        hhi = sum(w ** 2 for w in weights)
        # 映射到0-100的风险分
        return round(hhi * 100, 1)

    def _calc_expected_return(self, allocations: List[AllocationResult]) -> float:
        """估算组合预期收益"""
        if not allocations:
            return 0
        # 简单加权平均
        total = sum(a.weight for a in allocations)
        if total == 0:
            return 0
        weighted = sum(a.stock.confidence / 100 * a.weight for a in allocations)
        return round(weighted / total * 100, 1)

    def format_plan(self, plan: PortfolioPlan) -> str:
        """格式化组合计划为可读文本"""
        lines = [
            f"## 📊 今日投资组合计划",
            f"",
            f"💰 总资金: **{plan.total_capital:,.0f}元**",
            f"📊 使用资金: **{plan.used_capital:,.0f}元** ({plan.used_capital/plan.total_capital*100:.0f}%)",
            f"💵 预留现金: **{plan.cash_reserved:,.0f}元** ({plan.cash_reserved/plan.total_capital*100:.0f}%)",
            f"",
            f"### 买入清单",
        ]

        if not plan.allocations:
            lines.append("> ⚠️ 今日无符合分配条件的标的")
        else:
            for i, a in enumerate(plan.allocations, 1):
                s = a.stock
                lines.append(f"**{i}. {s.name} ({s.code})**")
                lines.append(f"> 买入价: ¥{s.price} | 数量: **{a.shares}股 ({a.shares//100}手)** | 金额: ¥{a.amount:,.0f}")
                lines.append(f"> 仓位: {a.weight}% | 止损: ¥{s.stop_loss} (亏{a.shares*(s.price-s.stop_loss):,.0f}元) | 止盈: ¥{s.stop_profit} (盈{a.shares*(s.stop_profit-s.price):,.0f}元)")
                lines.append(f"> 置信度: {s.confidence:.0f}% | {a.reason}")
                lines.append("")

        lines.append("### ⚙️ 操作步骤")
        lines.append("1. 打开券商APP → 条件单")
        for a in plan.allocations:
            s = a.stock
            lines.append(f"2. {s.name}: 买入价{s.price} 止损{s.stop_loss} 止盈{s.stop_profit}")
        lines.append(f"{len(plan.allocations)+2}. 关掉系统，该干嘛干嘛")

        if plan.notes:
            lines.append("")
            lines.append("### 📝 提示")
            for note in plan.notes:
                lines.append(f"- {note}")

        return '\n'.join(lines)


# 默认实例（10万资金）
allocator = PortfolioAllocator(total_capital=100000)
