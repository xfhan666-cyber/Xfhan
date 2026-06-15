"""
A股量化选股系统 - 早盘一键扫描版
"""
import os
for v in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy']:
    os.environ.pop(v, None)
os.environ['no_proxy'] = '*'

import requests
_orig = requests.Session.__init__
def _patched(self, *a, **kw):
    _orig(self, *a, **kw)
    self.trust_env = False
requests.Session.__init__ = _patched

import streamlit as st
import pandas as pd
from datetime import datetime
import time

st.set_page_config(page_title="A股量化选股", page_icon="📈", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""<style>
    .stApp { background: #0f172a; color: #e2e8f0; }
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }
    #MainMenu, footer, header { display: none !important; }
    .stTabs [data-baseweb="tab"] { background: #1e293b; color: #94a3b8; border-radius: 8px 8px 0 0; padding: 8px 14px; font-weight: 600; border: 1px solid #334155; border-bottom: none; }
    .stTabs [aria-selected="true"] { background: #1e40af; color: white; border-color: #3b82f6; }
    .big-button > button { font-size: 1.2rem !important; padding: 16px 40px !important; background: #ef4444 !important; font-weight: 800 !important; }
    .stButton > button { background: #3b82f6; color: white; border: none; border-radius: 8px; padding: 8px 20px; font-weight: 700; }
    .stButton > button:hover { background: #2563eb; }
    .metric-card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 10px 14px; text-align: center; }
    .metric-value { font-size: 1.2rem; font-weight: 800; color: #f8fafc; }
    .metric-label { font-size: 0.7rem; color: #94a3b8; }
    .signal-row { background: #1e293b; border-left: 3px solid #ef4444; border-radius: 0 8px 8px 0; padding: 10px 14px; margin: 6px 0; }
    [data-testid="stDataFrame"] th { background: #1e293b; color: #94a3b8; font-size: 0.8rem; }
</style>""", unsafe_allow_html=True)

# ============ 数据加载（按需，避免每次打开页面等待1分钟）============
@st.cache_data(ttl=600, show_spinner="正在获取A股实时数据，请稍候...")
def load_data():
    from data.fetcher import fetcher
    r = {'market': None, 'index': None, 'overview': {}, 'time': ''}
    t0 = time.time()
    df = fetcher.get_realtime_all_stocks()
    if df is not None and not df.empty:
        r['market'] = df
        r['time'] = datetime.now().strftime('%H:%M:%S')
    try:
        idx = fetcher.get_index_realtime()
        if not idx.empty and 'name' in idx.columns:
            r['index'] = idx.drop_duplicates(subset=['name'], keep='first')
    except Exception: pass
    try: r['overview'] = fetcher.get_market_overview(df=r['market'])
    except Exception: pass
    return r

# 初始化session state
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.market_data = None
    st.session_state.index_data = None
    st.session_state.overview = {}

def run_all_strategies(market_data):
    """运行全部7个策略，返回合并信号"""
    from strategies.multi_factor import MultiFactorStrategy
    from strategies.pb_roe import PBROEStrategy
    from strategies.trend_momentum import TrendMomentumStrategy
    from strategies.mean_reversion import MeanReversionStrategy
    from strategies.smallcap_growth import SmallCapGrowthStrategy
    from strategies.first_board import FirstBoardStrategy
    from strategies.limit_up import LimitUpStrategy
    from config import DEFAULT_STRATEGY_PARAMS

    strategies = [
        MultiFactorStrategy(DEFAULT_STRATEGY_PARAMS.get('multi_factor')),
        PBROEStrategy(DEFAULT_STRATEGY_PARAMS.get('pb_roe')),
        TrendMomentumStrategy(DEFAULT_STRATEGY_PARAMS.get('trend_momentum')),
        MeanReversionStrategy(DEFAULT_STRATEGY_PARAMS.get('mean_reversion')),
        SmallCapGrowthStrategy(DEFAULT_STRATEGY_PARAMS.get('smallcap_growth')),
        LimitUpStrategy(DEFAULT_STRATEGY_PARAMS.get('limit_up')),
        FirstBoardStrategy(DEFAULT_STRATEGY_PARAMS.get('first_board')),
    ]
    all_signals = []
    for s in strategies:
        try:
            s.set_market_data(market_data)
            result = s.run()
            all_signals.extend(result.signals)
        except Exception:
            pass

    # 合并同股票信号（多策略共识提升置信度）
    merged = {}
    for sig in all_signals:
        if sig.code not in merged:
            merged[sig.code] = sig
        else:
            merged[sig.code].confidence = min(98, merged[sig.code].confidence + 5)
            merged[sig.code].reason += f' | +{sig.strategy}'
    result = sorted(merged.values(), key=lambda x: x.confidence, reverse=True)
    return result

# ============ 主界面 ============
st.markdown(f"""
<div style="background:linear-gradient(135deg,#0f172a,#1e293b);border-bottom:2px solid #3b82f6;padding:10px 20px;display:flex;justify-content:space-between;align-items:center">
    <h1 style="font-size:1.2rem;color:#fbbf24;margin:0">📈 A股量化选股</h1>
    <span style="color:#94a3b8;font-size:0.8rem">{'✅ 已加载' if st.session_state.data_loaded else '⏳ 待加载'}</span>
</div>
""", unsafe_allow_html=True)

# ============ 三个Tab：扫描 · 回顾 · 帮助 ============
t1, t2, t3 = st.tabs(["⚡ 早盘扫描", "📊 大盘概览", "📖 使用帮助"])

# ===== Tab 1: 早盘扫描（核心功能）=====
with t1:
    st.markdown("### ⚡ 一键扫描今日机会")

    # 用户设置：总资金 + 风险偏好
    setting_col1, setting_col2 = st.columns(2)
    with setting_col1:
        total_capital = st.number_input(
            "💰 你的总资金（元）", min_value=10000, value=100000, step=10000,
            help="用于计算每只股票具体买多少股"
        )
    with setting_col2:
        risk_level = st.selectbox(
            "🎯 风险偏好",
            ['conservative', 'moderate', 'aggressive'],
            format_func=lambda x: {'conservative': '保守 (最多2只)',
                                   'moderate': '稳健 (最多3只)',
                                   'aggressive': '激进 (最多4只)'}[x],
            index=1
        )

    # === 核心：一键扫描（自动处理数据加载）===
    need_load = not st.session_state.data_loaded
    btn_label = "🚀 一键扫描今日买入机会" if not need_load else "🚀 一键扫描（含数据加载，约50秒）"

    if st.button(btn_label, type="primary", use_container_width=True):
        # Step 1: 加载数据（如果需要）
        if need_load:
            with st.spinner("📡 正在获取全市场实时数据（5514只股票），预计40-50秒..."):
                loaded = load_data()
                st.session_state.market_data = loaded['market']
                st.session_state.index_data = loaded['index']
                st.session_state.overview = loaded['overview']
                st.session_state.data_loaded = True
                st.session_state.market_time = loaded.get('time', '')
            market_df = loaded['market']
        else:
            market_df = st.session_state.market_data

        if market_df is None or market_df.empty:
            st.error("❌ 数据获取失败，请检查网络后点击刷新重试")
        else:
            # Step 2: 运行策略
            with st.spinner("🔍 正在运行7个策略分析全市场，大约需要30秒..."):
                signals = run_all_strategies(market_df)

            if not signals:
                st.warning("今日无符合条件的买入信号。当前市场环境不适合出击，空仓也是策略。")
            else:
                # Step 3: 仓位分配
                from portfolio.allocator import PortfolioAllocator
                allocator = PortfolioAllocator(total_capital=total_capital)
                plan = allocator.allocate(signals, risk_level=risk_level)

                st.success(f"扫描完成！共 {len(signals)} 个信号 → 精选 {len(plan.allocations)} 只")

                if plan.allocations:
                    st.subheader("📋 今日买入清单")
                    for i, a in enumerate(plan.allocations, 1):
                        s = a.stock
                        loss_amount = a.shares * (s.price - s.stop_loss)
                        profit_amount = a.shares * (s.stop_profit - s.price)
                        multi = '多策略共识' if '|' in s.reason else '单策略推荐'
                        st.markdown(f"""<div class="signal-row">
                            <div style="display:flex;justify-content:space-between;align-items:center">
                                <span>
                                    <strong style="font-size:1.15rem">#{i} {s.name}</strong>
                                    <span style="color:#94a3b8;font-size:0.9rem"> {s.code}</span>
                                    <span style="color:#fbbf24;font-size:0.8rem;margin-left:8px">🔥{s.confidence:.0f}%</span>
                                    <span style="color:#94a3b8;font-size:0.75rem"> {multi}</span>
                                </span>
                            </div>
                            <div style="margin-top:6px;font-size:0.85rem;color:#cbd5e1;display:flex;gap:20px;flex-wrap:wrap">
                                <span>买入价: <strong style="color:#fbbf24">¥{s.price}</strong></span>
                                <span>数量: <strong style="color:#60a5fa">{a.shares}股</strong> ({a.shares//100}手)</span>
                                <span>金额: <strong style="color:#60a5fa">¥{a.amount:,.0f}</strong> ({a.weight}%)</span>
                            </div>
                            <div style="margin-top:4px;font-size:0.85rem;color:#cbd5e1;display:flex;gap:20px">
                                <span>止损: <strong style="color:#ef4444">¥{s.stop_loss}</strong> (亏¥{loss_amount:,.0f})</span>
                                <span>止盈: <strong style="color:#10b981">¥{s.stop_profit}</strong> (盈¥{profit_amount:,.0f})</span>
                            </div>
                            <div style="font-size:0.78rem;color:#94a3b8;margin-top:2px">{s.reason[:120]}</div>
                        </div>""", unsafe_allow_html=True)

                    st.divider()
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("💰 总资金", f"¥{plan.total_capital:,.0f}")
                    c2.metric("📊 使用资金", f"¥{plan.used_capital:,.0f}", f"{plan.used_capital/plan.total_capital*100:.0f}%")
                    c3.metric("💵 预留现金", f"¥{plan.cash_reserved:,.0f}", f"{plan.cash_reserved/plan.total_capital*100:.0f}%")
                    c4.metric("⚡ 组合风险", f"{plan.risk_score}/100")

                    if plan.notes:
                        for note in plan.notes:
                            st.caption(f"💡 {note}")

                # 其他未入选信号
                allocated_codes = {a.stock.code for a in plan.allocations}
                remaining = [s for s in signals if s.code not in allocated_codes]
                strong_remaining = [s for s in remaining if s.confidence >= 75]
                if strong_remaining:
                    with st.expander(f"📋 其他信号 ({len(remaining)}个，因仓位/行业限制未入选)"):
                        for s in strong_remaining[:10]:
                            st.markdown(f"""<div class="signal-row" style="border-left-color:#6b7280">
                                <strong>{s.name} ({s.code})</strong> {s.confidence:.0f}% |
                                买{s.price} 止{s.stop_loss} 盈{s.stop_profit} | {s.reason[:80]}
                            </div>""", unsafe_allow_html=True)

        # 刷新数据按钮（扫描结果下方）
        if not need_load:
            st.divider()
            if st.button("🔄 刷新数据重新扫描"):
                st.session_state.data_loaded = False
                st.cache_data.clear()
                st.rerun()

    # 未扫描时的提示
    if not st.session_state.get('_last_scan_done', False) and st.session_state.data_loaded:
        n = len(st.session_state.market_data) if st.session_state.market_data is not None else 0
        st.caption(f"✅ 数据已就绪（{n}只股票），点击上方按钮开始扫描")

# ===== Tab 2: 大盘概览 =====
with t2:
    st.subheader("📊 市场数据")
    if not st.session_state.data_loaded:
        st.warning("请先在「早盘扫描」页加载市场数据")
    else:
        df = st.session_state.market_data
        if df is not None and not df.empty:
            st.caption(f"共{len(df)}只股票 | 更新时间{st.session_state.get('market_time', '')}")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**涨幅榜Top15**")
                dc = ['code','name','price','pct_change'] if all(c in df.columns for c in ['code','name','price','pct_change']) else None
                if dc:
                    st.dataframe(df.nlargest(15,'pct_change')[dc], hide_index=True, use_container_width=True)
            with col_b:
                st.markdown("**跌幅榜Top15**")
                if dc:
                    st.dataframe(df.nsmallest(15,'pct_change')[dc], hide_index=True, use_container_width=True)

            if 'pct_change' in df.columns:
                bins = [-100, -9.9, -5, -3, -1, 0, 1, 3, 5, 9.9, 100]
                labels = ['跌停','-5~-10%','-3~-5%','-1~-3%','0~-1%','0~+1%','+1~3%','+3~5%','+5~10%','涨停']
                df['rng'] = pd.cut(df['pct_change'], bins=bins, labels=labels)
                dist = df['rng'].value_counts().reindex(labels, fill_value=0)
                st.bar_chart(pd.DataFrame({'区间':labels,'数量':dist.values}).set_index('区间'), use_container_width=True)

# ===== Tab 3: 使用帮助 =====
with t3:
    st.markdown("""
    ## 📖 使用说明

    ### 你只需要做这些
    ```
    1. 每个交易日 9:25 后打开本系统
    2. 点「⚡ 早盘扫描」→ 点「一键扫描」
    3. 查看强信号（🔥标记），选2-3只你熟悉的
    4. 打开券商APP，设好条件单：
       - 买入价 = 系统建议价
       - 止损价 = 系统止损价（必须设！）
       - 止盈价 = 系统止盈价
    5. 关掉系统，该干嘛干嘛
    ```

    ### 信号怎么看
    - 🔥 **75%以上**：强信号，多策略共识，重点考虑
    - 🟡 **55-75%**：中等信号，结合自己判断
    - ❌ **55%以下**：弱信号，忽略

    ### 大盘环境自动判断
    系统会根据涨跌比和涨停数量自动告诉你今天适合什么策略：
    - 🟢 强势 → 适合趋势、打板
    - 🟡 震荡 → 适合多因子、价值
    - 🟠 弱势 → 适合超跌反弹、防御
    - 🔴 极端 → 建议空仓

    ### 核心原则
    1. **每天最多只做2-3只**，别贪多
    2. **止损必须设**，亏3%就认，别扛
    3. **次日开盘检查**昨天的单子有没有触发
    4. **市场不好时空仓**，不买也是赚钱

    ### 常见问题
    **Q: 为什么有时候扫不出股票？**
    市场不好，策略全都判断不适合买入。这是对的——强行买才是错的。

    **Q: 需要一直开着吗？**
    不需要。开盘扫一次，设好条件单就关。你在券商设的条件单会自动执行。

    **Q: 回测、自定义策略在哪？**
    高级功能入口在左侧保留。日常使用只需要「早盘扫描」这一个页面。
    """)
