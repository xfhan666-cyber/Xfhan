"""
回测对比 - 基于真实历史数据的策略回测
"""
import streamlit as st
import pandas as pd
from backtest.real_engine import real_engine

STRATEGY_OPTIONS = {
    'trend': '趋势动量 (MA均线交叉)',
    'reversion': '超跌反弹 (均值回归)',
    'both': '全部策略对比',
}

POOL_OPTIONS = {
    'top_volume': '成交额Top50（全A股活跃股）',
    'hs300': '沪深300成分股（大盘蓝筹）',
    'zz500': '中证500成分股（中盘成长）',
}


def show():
    st.subheader("📈 策略回测（真实历史数据）")

    st.info("💡 基于AKShare真实日K线数据回测。数据获取需要1-3分钟，请耐心等待。首次运行会下载历史数据。")

    # 策略选择
    col1, col2, col3 = st.columns(3)
    with col1:
        strategy_type = st.selectbox(
            "回测策略",
            list(STRATEGY_OPTIONS.keys()),
            format_func=lambda x: STRATEGY_OPTIONS[x],
            index=2  # 默认全部
        )
    with col2:
        stock_pool = st.selectbox(
            "股票池",
            list(POOL_OPTIONS.keys()),
            format_func=lambda x: POOL_OPTIONS[x],
            index=0
        )
    with col3:
        lookback = st.selectbox(
            "回测周期",
            ['近6个月', '近1年', '近2年'],
            index=1
        )

    lookback_days = {'近6个月': 126, '近1年': 252, '近2年': 504}[lookback]

    # 回测按钮
    if st.button("🔬 开始真实回测", type="primary", use_container_width=True):
        with st.spinner(f"正在获取真实历史数据并运行回测（预计1-3分钟）...\n\n"
                        f"• 获取{POOL_OPTIONS[stock_pool]}\n"
                        f"• 下载{lookback}日K线数据\n"
                        f"• 运行{STRATEGY_OPTIONS[strategy_type]}"):

            results = real_engine.run_full_backtest(
                strategy_type=strategy_type,
                lookback_days=lookback_days,
                stock_pool=stock_pool,
                pool_size=50
            )

        if 'error' in results:
            st.error(f"回测失败: {results['error']}")
            return

        if not results:
            st.warning("回测未产生结果，可能数据不足")
            return

        # 汇总对比表
        st.subheader("📊 回测结果对比")

        rows = []
        for name, r in results.items():
            strategy_label = {'trend': '趋势动量', 'reversion': '超跌反弹'}.get(name, name)
            rows.append({
                '策略': strategy_label,
                '累计收益(%)': r.get('total_return', 0),
                '年化收益(%)': r.get('annual_return', 0),
                '夏普比率': r.get('sharpe_ratio', 0),
                '最大回撤(%)': r.get('max_drawdown', 0),
                '胜率(%)': r.get('win_rate', 0),
                '交易次数': r.get('total_trades', 0),
                '盈亏比': r.get('profit_loss_ratio', 0),
                '基准(沪深300)(%)': r.get('benchmark_return', 0),
                '超额收益(%)': r.get('excess_return', 0),
            })

        comparison = pd.DataFrame(rows)

        # 格式化
        styled = comparison.style.background_gradient(
            subset=['夏普比率', '累计收益(%)', '超额收益(%)'], cmap='RdYlGn'
        ).background_gradient(
            subset=['最大回撤(%)'], cmap='RdYlGn_r'
        ).format({
            '累计收益(%)': '{:.2f}', '年化收益(%)': '{:.2f}',
            '夏普比率': '{:.2f}', '最大回撤(%)': '{:.2f}',
            '胜率(%)': '{:.1f}', '超额收益(%)': '{:.2f}',
            '盈亏比': '{:.2f}', '基准(沪深300)(%)': '{:.2f}',
        })

        st.dataframe(styled, use_container_width=True, hide_index=True)

        # 最佳策略
        if 'sharpe_ratio' in comparison.columns:
            valid = comparison[comparison['夏普比率'] != 0]
            if not valid.empty:
                best = valid.loc[valid['夏普比率'].idxmax()]
                st.success(
                    f"🏆 最优策略: **{best['策略']}** | "
                    f"夏普: {best['夏普比率']} | "
                    f"累计收益: {best['累计收益(%)']}% | "
                    f"超额收益: {best['超额收益(%)']}%"
                )

        # 各策略详细指标
        st.subheader("📋 详细指标")
        for name, r in results.items():
            label = {'trend': '趋势动量', 'reversion': '超跌反弹'}.get(name, name)
            with st.expander(
                f"{label} | 累计收益: {r.get('total_return', 0)}% | "
                f"夏普: {r.get('sharpe_ratio', 0)} | "
                f"最大回撤: -{r.get('max_drawdown', 0)}%"
            ):
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("累计收益", f"{r.get('total_return', 0)}%")
                c2.metric("年化收益", f"{r.get('annual_return', 0)}%")
                c3.metric("夏普比率", f"{r.get('sharpe_ratio', 0)}")
                c4.metric("最大回撤", f"-{r.get('max_drawdown', 0)}%")
                c5.metric("胜率", f"{r.get('win_rate', 0)}%")

                c6, c7, c8, c9, _ = st.columns(5)
                c6.metric("交易次数", r.get('total_trades', 0))
                c7.metric("盈亏比", f"{r.get('profit_loss_ratio', 0)}")
                c8.metric("超额收益", f"{r.get('excess_return', 0)}%")
                c9.metric("基准收益", f"{r.get('benchmark_return', 0)}%")

                # 显示净值曲线（如果可用）
                daily_vals = r.get('daily_values', [])
                if daily_vals and len(daily_vals) > 1:
                    st.caption("净值曲线（最近一年）")
                    st.line_chart(pd.DataFrame({'净值': daily_vals}))

        # 交易记录
        st.subheader("📝 近期交易记录（前20笔）")
        for name, r in results.items():
            trades = r.get('trades', [])
            if trades:
                with st.expander(f"{name} 交易记录 ({len(trades)}笔)"):
                    st.dataframe(pd.DataFrame(trades), use_container_width=True, hide_index=True)

    # 诚实披露
    with st.expander("⚠️ 回测局限性与诚实披露"):
        st.markdown("""
        ### 本回测引擎的局限性

        | 策略类型 | 回测可行性 | 说明 |
        |---------|-----------|------|
        | **趋势动量** | ✅ 完整回测 | 基于真实K线的MA均线交叉，数据可靠 |
        | **超跌反弹** | ✅ 完整回测 | 基于真实K线的跌幅统计，数据可靠 |
        | **多因子综合** | ⚠️ 部分回测 | PE/PB/ROE等基本面数据历史覆盖不全 |
        | **PB-ROE价值** | ⚠️ 部分回测 | 财报数据季度更新，回测精度受限 |
        | **小盘成长** | ⚠️ 部分回测 | 营收增长率等财务数据历史不完整 |
        | **涨停板/首板** | ❌ 无法精确回测 | 需要逐笔成交数据和精确封板时间 |

        ### 回测注意事项
        - **过拟合风险**: 历史表现好≠未来表现好
        - **幸存者偏差**: 股票池不包含已退市股票
        - **滑点/手续费**: 当前回测未计入交易成本（约0.1-0.3%）
        - **流动性**: 未考虑大资金对价格的冲击
        - **市场环境变化**: 注册制改革后市场结构已变

        ### 建议
        - 回测年化收益 > 15% 且 夏普 > 1.0 的策略才有实盘价值
        - 最大回撤 > 25% 的策略需要做仓位控制
        - 实盘前先在模拟盘跑1个月验证
        """)

    # 回测指标说明
    with st.expander("📖 回测指标说明"):
        st.markdown("""
        | 指标 | 说明 | 优秀标准 | 及格标准 |
        |------|------|---------|---------|
        | **累计收益** | 整个回测期的总收益率 | >30%/年 | >10%/年 |
        | **年化收益** | 折算为年化的收益率 | >20% | >8% |
        | **夏普比率** | 收益/风险比，越高越好 | >1.5 | >0.8 |
        | **最大回撤** | 最大亏损幅度，越低越好 | <15% | <25% |
        | **胜率** | 盈利交易占比 | >55% | >45% |
        | **盈亏比** | 平均盈利/平均亏损 | >2.0 | >1.2 |
        | **超额收益** | 相对沪深300的超额收益 | >10%/年 | >3%/年 |
        """)
