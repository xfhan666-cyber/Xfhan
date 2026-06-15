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
    shares: int
    amount: float
    weight: float
    reason: str          # 精选理由（为什么选这只）
    rank_info: str = ''  # 排名详情


@dataclass
class PortfolioPlan:
    """组合计划"""
    total_capital: float = 100000
    used_capital: float = 0
    cash_reserved: float = 0
    allocations: List[AllocationResult] = field(default_factory=list)
    risk_score: float = 0
    expected_return: float = 0
    notes: List[str] = field(default_factory=list)


class PortfolioAllocator:
    """
    投资组合分配器

    精选逻辑：
    1. 置信度筛选（按风险偏好设阈值）
    2. 多策略共识加分（同一股票被多个策略推荐 → 置信度+5）
    3. 行业/策略类型分散（避免同质化）
    4. 等风险预算分配仓位
    """

    def __init__(self, total_capital: float = 100000):
        self.total_capital = total_capital
        self.max_single_position = 0.15     # 单票最大仓位15%
        self.cash_reserve_ratio = 0.20      # 预留现金20%
        self.max_positions = 4
        self.lot_size = 100                 # A股1手=100股

    def allocate(self, signals: List[TradeSignal],
                 risk_level: str = 'moderate') -> PortfolioPlan:
        plan = PortfolioPlan(total_capital=self.total_capital)

        if not signals:
            plan.notes.append("无可用信号，建议空仓等待")
            return plan

        # === 第1步：按风险偏好筛选 ===
        if risk_level == 'conservative':
            confidence_min = 75
            max_positions = 2
            cash_ratio = 0.35
            require_multi = True  # 保守模式要求多策略共识
        elif risk_level == 'aggressive':
            confidence_min = 55
            max_positions = 4
            cash_ratio = 0.10
            require_multi = False
        else:
            confidence_min = 65
            max_positions = 3
            cash_ratio = 0.20
            require_multi = False

        self.max_positions = max_positions
        self.cash_reserve_ratio = cash_ratio

        # 按置信度筛选
        filtered = [s for s in signals if s.confidence >= confidence_min]
        if require_multi:
            # 保守模式额外要求：必须被2个以上策略推荐
            filtered = [s for s in filtered if '|' in s.reason]

        if not filtered:
            highest = max(signals, key=lambda s: s.confidence)
            plan.notes.append(
                f"当前模式({risk_level})要求置信度≥{confidence_min}%，"
                f"最高仅{highest.confidence:.0f}%({highest.name})，不满足条件。"
                f"建议：切换为更激进模式，或等待更好机会。"
            )
            return plan

        # === 第2步：多维度精选 ===
        # 对每个候选计算综合评分
        scored = []
        for s in filtered:
            score = self._calc_pick_score(s)
            scored.append((score, s))

        scored.sort(key=lambda x: x[0], reverse=True)

        # === 第3步：分散化选取（优先策略类型分散，其次行业分散）===
        selected = self._diversify_selection(scored, max_positions)

        # === 第4步：仓位分配 ===
        available = self.total_capital * (1 - self.cash_reserve_ratio)
        allocations = self._allocate_positions(selected, available, risk_level)

        plan.allocations = allocations
        plan.used_capital = sum(a.amount for a in allocations)
        plan.cash_reserved = self.total_capital - plan.used_capital
        plan.risk_score = self._calc_portfolio_risk(allocations)
        plan.expected_return = self._calc_expected_return(allocations)

        # 添加说明
        plan.notes.append(
            f"从{len(signals)}个信号中筛选{len(filtered)}个达标 → "
            f"精选{len(allocations)}只（{risk_level}模式，置信度≥{confidence_min}%）"
        )

        return plan

    def _calc_pick_score(self, s: TradeSignal) -> float:
        """
        计算精选评分（用于横向对比）

        评分维度：
        - 置信度基础分：0-100
        - 多策略共识加分：每个额外策略+10分
        - 策略质量加分：不同策略类型权重不同
        """
        score = float(s.confidence)

        # 多策略共识加分
        strategy_count = s.reason.count('|') + 1
        if strategy_count >= 3:
            score += 20  # 3个以上策略同时推荐 → 大幅加分
        elif strategy_count >= 2:
            score += 10  # 2个策略共识

        # 策略类型加分（基本面策略 > 技术面策略）
        reason_lower = s.reason.lower()
        if any(kw in reason_lower for kw in ['pb-roe', '多因子', '价值']):
            score += 5  # 基本面策略更可靠

        return score

    def _diversify_selection(self, scored: List[Tuple[float, TradeSignal]],
                              max_picks: int) -> List[TradeSignal]:
        """
        分散化选取：优先保证策略类型多样性，其次行业多样性

        策略：轮询选取，每轮从不同策略组中取最佳
        """
        if not scored:
            return []

        # 提取每只股票的策略来源
        def get_strategy_types(signal: TradeSignal) -> List[str]:
            """从reason中提取策略名"""
            types = []
            reason = signal.reason
            # 格式：'[策略名]原策略名' 或 '原策略名'
            for prefix in ['[多因子]', '[PB-ROE]', '[趋势动量]', '[超跌反弹]',
                           '[小盘成长]', '[涨停板]', '[首板打板]']:
                if prefix in reason:
                    types.append(prefix.strip('[]'))
            if not types:
                # 从 strategy 字段提取
                types.append(signal.strategy)
            return types

        # 按策略类型分组
        type_groups: Dict[str, List[Tuple[float, TradeSignal]]] = {}
        for score, s in scored:
            for stype in get_strategy_types(s):
                if stype not in type_groups:
                    type_groups[stype] = []
                type_groups[stype].append((score, s))

        # 如果没有足够的策略类型多样性（所有股票在同一组），直接按分数选
        if len(type_groups) <= 1:
            seen = set()
            result = []
            for score, s in scored:
                if len(result) >= max_picks:
                    break
                if s.code not in seen:
                    result.append(s)
                    seen.add(s.code)
            return result

        # 轮询每个策略组，每轮取该组最佳
        selected = []
        seen_codes = set()
        type_queue = sorted(type_groups.keys(),
                           key=lambda k: max(sc for sc, _ in type_groups[k]),
                           reverse=True)

        while len(selected) < max_picks:
            added_this_round = False
            for stype in type_queue:
                if len(selected) >= max_picks:
                    break
                # 取该策略组中还没被选的最佳股票
                group = [(sc, s) for sc, s in type_groups[stype]
                        if s.code not in seen_codes]
                if group:
                    best = max(group, key=lambda x: x[0])
                    selected.append(best[1])
                    seen_codes.add(best[1].code)
                    added_this_round = True

            if not added_this_round:
                break  # 没有更多可选的

        return selected

    def _allocate_positions(self, stocks: List[TradeSignal],
                             available: float,
                             risk_level: str) -> List[AllocationResult]:
        """仓位分配"""
        if not stocks:
            return []

        n = len(stocks)
        # 等权为基础，置信度微调
        base_weight = min(1.0 / n, self.max_single_position)

        confidences = [s.confidence for s in stocks]
        avg_conf = sum(confidences) / n

        results = []
        for i, stock in enumerate(stocks):
            # 置信度偏离均值做±20%调整
            bias = 1.0 + (stock.confidence - avg_conf) / 250
            bias = max(0.8, min(1.2, bias))
            weight = min(base_weight * bias, self.max_single_position)
            amount = available * weight
            price = stock.price

            # 按手取整
            lots = max(1, math.floor(amount / price / self.lot_size))
            shares = lots * self.lot_size
            actual_amount = shares * price

            # 生成精选理由
            reason, rank_info = self._build_pick_reason(stock, i+1, n, risk_level)

            results.append(AllocationResult(
                stock=stock,
                shares=shares,
                amount=round(actual_amount, 2),
                weight=round(actual_amount / self.total_capital * 100, 1),
                reason=reason,
                rank_info=rank_info
            ))

        return results

    def _build_pick_reason(self, signal: TradeSignal, rank: int,
                            total: int, risk_level: str) -> Tuple[str, str]:
        """
        构建精选理由——解释为什么选这只股票

        返回: (简短理由, 详细排名信息)
        """
        parts = []

        # 1. 排名信息
        parts.append(f"综合评分第{rank}/{total}名")

        # 2. 策略来源
        strategy_count = signal.reason.count('|') + 1
        if strategy_count >= 3:
            parts.append(f"{strategy_count}个策略同时推荐（高度共识）")
        elif strategy_count >= 2:
            parts.append(f"{strategy_count}个策略共识推荐")
        else:
            parts.append(f"单策略推荐：{signal.strategy}")

        # 3. 置信度解读
        if signal.confidence >= 85:
            parts.append("信号极强，历史回测胜率较高")
        elif signal.confidence >= 75:
            parts.append("信号较强，值得重点关注")
        elif signal.confidence >= 65:
            parts.append("信号中等，可适量参与")
        else:
            parts.append("信号一般，轻仓试探")

        # 4. 估值/技术特征（从reason和factors中提取）
        factors = signal.factors
        if factors:
            score_val = factors.get('score', 0)
            if score_val > 80:
                parts.append(f"策略得分{score_val:.0f}/100，名列前茅")

        # 5. 风险提示
        if '⚠' in signal.reason or '谨慎' in signal.reason:
            parts.append("⚠️ 注意风险信号，严格止损")

        reason = '；'.join(parts[:4])  # 前4条作为简短理由

        # 详细排名信息
        rank_details = [
            f"策略: {signal.strategy}",
            f"置信度: {signal.confidence:.0f}%",
            f"策略共识数: {strategy_count}",
        ]
        if factors:
            for k, v in factors.items():
                if k != 'score':
                    rank_details.append(f"{k}: {v}")
        rank_info = ' | '.join(rank_details)

        return reason, rank_info

    def _calc_portfolio_risk(self, allocations: List[AllocationResult]) -> float:
        if not allocations:
            return 0
        weights = [a.weight / 100 for a in allocations]
        hhi = sum(w ** 2 for w in weights)
        return round(hhi * 100, 1)

    def _calc_expected_return(self, allocations: List[AllocationResult]) -> float:
        if not allocations:
            return 0
        total_w = sum(a.weight for a in allocations)
        if total_w == 0:
            return 0
        return round(sum(a.stock.confidence / 100 * a.weight for a in allocations) / total_w * 100, 1)


# 默认实例
allocator = PortfolioAllocator(total_capital=100000)
