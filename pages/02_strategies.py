"""
策略中心 - 选择策略查看实时选股结果（使用共享缓存，秒加载）
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from strategies.multi_factor import MultiFactorStrategy
from strategies.pb_roe import PBROEStrategy
from strategies.trend_momentum import TrendMomentumStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.smallcap_growth import SmallCapGrowthStrategy
from strategies.limit_up import LimitUpStrategy
from strategies.first_board import FirstBoardStrategy
from config import DEFAULT_STRATEGY_PARAMS


STRATEGY_INFO = {
    'multi_factor': {'name': '多因子综合打分', 'icon': '🎯', 'color': '#3b82f6',
                     'desc': 'PE+PB+ROE+增速+动量+换手+波动，行业中性化百分位打分，每月调仓，适合中长期配置',
                     'style': '基本面+技术面', 'hold': '1-3个月'},
    'pb_roe': {'name': 'PB-ROE价值精选', 'icon': '💎', 'color': '#10b981',
               'desc': '低PB+高ROE+盈利稳定，按性价比排名，每季调仓，适合价值投资',
               'style': '价值投资', 'hold': '3-6个月'},
    'trend_momentum': {'name': '趋势动量+资金流', 'icon': '🚀', 'color': '#f59e0b',
                       'desc': '均线多头排列+主力资金流入+放量突破，中短线趋势跟踪，适合波段操作',
                       'style': '趋势跟踪', 'hold': '1-4周'},
    'mean_reversion': {'name': '超跌反弹', 'icon': '🎢', 'color': '#ef4444',
                       'desc': '严重超跌+缩量止跌+底部形态，短线反转博弈，快进快出',
                       'style': '反转博弈', 'hold': '3-10天'},
    'smallcap_growth': {'name': '小盘成长轮动', 'icon': '🌱', 'color': '#8b5cf6',
                        'desc': '市值<200亿+高成长+机构关注，中证1000风格，适合中小盘行情',
                        'style': '成长轮动', 'hold': '2-4周'},
    'limit_up': {'name': '涨停板跟踪', 'icon': '🔥', 'color': '#f97316',
                 'desc': '分析涨停板质量，筛选首板连板潜力股，博弈次日溢价，适合超短线',
                 'style': '事件驱动', 'hold': '1-2天'},
    'first_board': {'name': '⚡ 首板打板策略', 'icon': '⚡', 'color': '#ec4899',
                    'desc': '早盘封板+题材共振≥3只+市值30-80亿+量比≥3+底部形态，次日必卖，严格风控',
                    'style': '打板战法', 'hold': '次日必卖'},
}


def run_strategy(strategy_key, market_data):
    strategy_map = {
        'multi_factor': MultiFactorStrategy,
        'pb_roe': PBROEStrategy,
        'trend_momentum': TrendMomentumStrategy,
        'mean_reversion': MeanReversionStrategy,
        'smallcap_growth': SmallCapGrowthStrategy,
        'limit_up': LimitUpStrategy,
        'first_board': FirstBoardStrategy,
    }
    cls = strategy_map.get(strategy_key)
    if not cls:
        return None
    params = DEFAULT_STRATEGY_PARAMS.get(strategy_key, {})
    strategy = cls(params)
    strategy.set_market_data(market_data)
    return strategy.run()


def show():
    st.subheader("🔮 策略中心 — 选择策略查看选股结果")

    # 策略选择指南
    with st.expander("🤔 不知道用哪个策略？点击看推荐", expanded=False):
        st.markdown("""
        ### 按你的情况选择

        | 你的偏好 | 推荐策略 | 为什么 |
        |---------|---------|--------|
        | **我是新手，求稳** | 🎯 多因子综合打分 | 7因子分散，不依赖单一逻辑，最全面 |
        | **我偏价值投资** | 💎 PB-ROE价值精选 | 找低估+高ROE的好公司，安全边际高 |
        | **我想做波段** | 🚀 趋势动量+资金流 | 跟主力资金+均线趋势，顺势而为 |
        | **大跌后抄底** | 🎢 超跌反弹 | 急跌后的反弹机会，快进快出 |
        | **中小盘行情** | 🌱 小盘成长轮动 | 市值<200亿高弹性股票 |
        | **打板/超短线** | ⚡ 首板打板策略 | 板块共振+早盘封板，次日必卖 |

        ### 每日操作建议
        ```
        09:00  打开系统，查看仪表盘了解大盘环境
        09:25  竞价结束，切到策略中心，选「首板打板」看今天哪些板块共振
        09:30  开盘后，选「趋势动量」找强势股
        10:00  切到「交易信号」Tab，点「扫描全市场」，看综合推荐
        14:30  尾盘再看看「超跌反弹」有没有尾盘偷袭机会
        15:00  收盘，看信号汇总，决定明天操作
        ```

        ⚠️ **不是每个策略每天都能选出股票**——这是正常的！比如趋势策略在下跌市就没有信号，超跌策略在牛市中就选不出股。选不出股=该策略不适合当前市场。
        """)

    market_data = st.session_state.get('market_data')
    if market_data is None or market_data.empty:
        st.error("市场数据未加载，请先回到仪表盘等待数据加载完成")
        return

    st.success(f"✅ {len(market_data)}只股票已就绪，选择策略后点击运行")

    # 策略选择
    selected = st.selectbox(
        "选择量化策略",
        list(STRATEGY_INFO.keys()),
        format_func=lambda x: f"{STRATEGY_INFO[x]['icon']} {STRATEGY_INFO[x]['name']} — {STRATEGY_INFO[x]['desc'][:60]}..."
    )

    info = STRATEGY_INFO[selected]
    st.markdown(f"### {info['icon']} {info['name']}")
    st.caption(f"风格: {info['style']} | 建议持仓周期: {info['hold']} | {info['desc']}")

    if st.button("🚀 运行策略", type="primary", use_container_width=True):
        with st.spinner(f"正在运行 {info['name']}，分析{len(market_data)}只股票..."):
            result = run_strategy(selected, market_data)

        if result is None or result.selected_stocks.empty:
            st.warning("⚠️ 当前无符合条件的股票。可能是市场环境不符合该策略的筛选条件，尝试其他策略。")
            st.info("💡 不同策略适合不同市场环境：震荡市用PB-ROE，牛市用趋势动量，急跌后用超跌反弹")
            return

        stocks = result.selected_stocks
        signals = result.signals

        # 得分排名图
        if 'score' in stocks.columns:
            top_chart = stocks.head(15)[['name', 'score']].copy()
            top_chart = top_chart.sort_values('score')
            st.bar_chart(top_chart.set_index('name'), use_container_width=True)

        # 选股列表
        st.subheader(f"📋 选股结果 (共{len(stocks)}只)")
        display_cols = [c for c in ['code', 'name', 'price', 'pct_change', 'score', 'turnover', 'pe_ratio', 'pb_ratio', 'market_cap', 'amount'] if c in stocks.columns]
        st.dataframe(stocks[display_cols].head(30), use_container_width=True, hide_index=True,
                     column_config={
                         'code': '代码', 'name': '名称',
                         'price': st.column_config.NumberColumn('最新价', format='%.2f'),
                         'pct_change': st.column_config.NumberColumn('涨跌%', format='%.2f'),
                         'score': st.column_config.NumberColumn('得分', format='%.1f'),
                         'turnover': st.column_config.NumberColumn('换手%', format='%.2f'),
                         'pe_ratio': st.column_config.NumberColumn('PE', format='%.1f'),
                         'pb_ratio': st.column_config.NumberColumn('PB', format='%.1f'),
                         'market_cap': st.column_config.NumberColumn('总市值', format='%.0f'),
                         'amount': st.column_config.NumberColumn('成交额', format='%.0f'),
                     })

        # 交易信号
        if signals:
            st.subheader(f"📶 交易信号 ({len(signals)}条)")
            for s in signals[:8]:
                bg = '#1e293b' if s.action == 'BUY' else '#1a2e1a'
                border = '#ef4444' if s.action == 'BUY' else '#10b981'
                st.markdown(f"""
                <div style="background:{bg};border-left:3px solid {border};border-radius:8px;padding:12px;margin:6px 0">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <strong style="font-size:1.05rem">{s.name} <span style="color:#94a3b8;font-weight:400">{s.code}</span></strong>
                        <span style="color:{border};font-weight:700">{'🔴 买入' if s.action=='BUY' else '🟢 卖出'}</span>
                    </div>
                    <div style="margin-top:6px;font-size:0.85rem;color:#cbd5e1">
                        置信度: <strong style="color:#fbbf24">{s.confidence:.0f}%</strong> |
                        建议价: <strong>{s.price}</strong> |
                        止损: {s.stop_loss} | 止盈: {s.stop_profit} |
                        策略: {s.strategy}
                    </div>
                    <div style="margin-top:4px;font-size:0.8rem;color:#94a3b8">📝 {s.reason}</div>
                </div>
                """, unsafe_allow_html=True)

        st.text(result.summary)
