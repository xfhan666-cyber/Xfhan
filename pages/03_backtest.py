"""
回测对比 - 7个策略回测指标对比分析
"""
import streamlit as st
import pandas as pd
from backtest.engine import engine
from backtest.analyzer import BacktestAnalyzer


STRATEGY_NAMES = [
    '多因子综合打分', 'PB-ROE价值精选', '趋势动量+资金流',
    '超跌反弹', '小盘成长轮动', '涨停板跟踪', '首板打板策略'
]


def show():
    st.subheader("📈 策略回测对比")

    st.info("💡 选择策略进行回测对比。回测基于历史模拟数据，用于评估策略的相对表现和风险特征。实盘表现可能不同。")

    selected = st.multiselect(
        "选择要对比的策略（可多选）",
        STRATEGY_NAMES,
        default=STRATEGY_NAMES[:5]
    )

    col1, col2 = st.columns(2)
    with col1:
        period = st.selectbox("回测周期", ['近1年', '近2年', '近3年', '近5年'], index=0)
    with col2:
        benchmark = st.selectbox("对比基准", ['沪深300', '中证500', '中证A500'], index=0)

    if st.button("🔬 开始回测对比", type="primary", use_container_width=True):
        if not selected:
            st.warning("请至少选择一个策略")
            return

        with st.spinner("正在运行回测分析..."):
            results = []
            for name in selected:
                result = engine.generate_sample_backtest(name)
                results.append(result)

        if results:
            # 对比表格
            st.subheader("📊 策略回测对比表")
            comparison = BacktestAnalyzer.compare_strategies(results)

            # 格式化显示
            styled = comparison.style.background_gradient(subset=['夏普比率', '累计收益(%)'], cmap='RdYlGn')\
                                    .background_gradient(subset=['最大回撤(%)'], cmap='RdYlGn_r')\
                                    .format({
                                        '累计收益(%)': '{:.2f}', '年化收益(%)': '{:.2f}',
                                        '夏普比率': '{:.2f}', '最大回撤(%)': '{:.2f}',
                                        '胜率(%)': '{:.1f}', '超额收益(%)': '{:.2f}',
                                        '盈亏比': '{:.2f}'
                                    })
            st.dataframe(styled, use_container_width=True, hide_index=True)

            # 最佳策略
            best = max(results, key=lambda r: r.sharpe_ratio)
            st.success(f"🏆 夏普比率最优: **{best.strategy_name}** (夏普={best.sharpe_ratio}, 累计收益={best.total_return}%)")

            # 各策略详细指标
            st.subheader("📋 各策略详细指标")
            for r in results:
                with st.expander(f"{r.strategy_name} | 累计收益: {r.total_return}% | 夏普: {r.sharpe_ratio} | 最大回撤: {r.max_drawdown}%"):
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("累计收益", f"{r.total_return}%")
                    c2.metric("年化收益", f"{r.annual_return}%")
                    c3.metric("夏普比率", f"{r.sharpe_ratio}")
                    c4.metric("最大回撤", f"-{r.max_drawdown}%")
                    c5.metric("胜率", f"{r.win_rate}%")

                    c6, c7, c8, c9, _ = st.columns(5)
                    c6.metric("交易次数", r.total_trades)
                    c7.metric("盈亏比", f"{r.profit_loss_ratio}")
                    c8.metric("超额收益", f"{r.excess_return}%")
                    c9.metric("基准收益", f"{r.benchmark_return}%")

    # 回测参数说明
    with st.expander("📖 回测指标说明"):
        st.markdown("""
        | 指标 | 说明 | 优秀标准 |
        |------|------|---------|
        | **累计收益** | 整个回测期的总收益率 | >20%/年 |
        | **年化收益** | 折算为年化的收益率 | >15% |
        | **夏普比率** | 收益/风险比，越高越好 | >1.5 |
        | **最大回撤** | 最大亏损幅度，越低越好 | <15% |
        | **胜率** | 盈利交易占比 | >55% |
        | **盈亏比** | 平均盈利/平均亏损 | >2.0 |
        | **超额收益** | 相对基准的超额收益 | >5%/年 |
        """)
