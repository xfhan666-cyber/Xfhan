"""
A股量化选股系统 — 市场温度计 → 板块轮动 → 个股精选
"""
import os, re
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
import numpy as np
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="A股量化选股", page_icon="📈", layout="wide",
                   initial_sidebar_state="collapsed")

# ============================================================
# CSS — 王者荣耀蓝红金 · 高对比度
# ============================================================
st.markdown("""
<style>
    :root {
        --bg-deep: #050d18;
        --bg-primary: #091525;
        --bg-card: #0f1e38;
        --bg-elevated: #162848;
        --border: #223d60;
        --blue: #3b82f6;
        --blue-glow: #60a5fa;
        --blue-light: #b4d4ff;
        --red: #e53935;
        --red-glow: #f55a55;
        --red-light: #ff8a80;
        --gold: #e6b422;
        --gold-light: #ffd54f;
        --text: #f8f9fc;
        --text-dim: #c0c6d4;
        --text-muted: #8a92a4;
    }

    .stApp { background: var(--bg-deep) !important; }
    .main { background: var(--bg-deep) !important; }
    section[data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }
    #MainMenu, footer, header { display: none !important; }

    div[data-baseweb="select"] > div, div[data-baseweb="popover"],
    div[data-baseweb="menu"], div[data-baseweb="option"] {
        background: var(--bg-elevated) !important; border-color: var(--border) !important; color: var(--text) !important;
    }
    li[data-baseweb="option"]:hover { background: var(--blue) !important; }
    input, textarea, .stNumberInput input, [data-baseweb="input"] input, [data-baseweb="input"] > div {
        background: var(--bg-elevated) !important; color: var(--text) !important;
        border: 1px solid var(--border) !important; border-radius: 6px !important;
    }
    .stSelectbox > div > div { background: var(--bg-elevated) !important; border-color: var(--border) !important; }

    .streamlit-expanderHeader {
        background: var(--bg-card) !important; border: 1px solid var(--border) !important;
        border-radius: 8px !important; color: var(--text) !important; font-weight: 600 !important;
    }
    .streamlit-expanderContent {
        background: var(--bg-primary) !important; border: 1px solid var(--border) !important;
        border-top: none !important; border-radius: 0 0 8px 8px !important; padding: 16px !important;
    }

    .stTabs [data-baseweb="tab"] {
        background: var(--bg-card) !important; color: var(--text-dim) !important;
        border-radius: 8px 8px 0 0 !important; padding: 10px 20px !important;
        font-weight: 600 !important; border: 1px solid var(--border) !important; border-bottom: none !important;
    }
    .stTabs [aria-selected="true"] { background: var(--blue) !important; color: #fff !important; border-color: var(--blue) !important; }

    .stButton > button {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
        color: #fff !important; border: none !important; border-radius: 6px !important;
        padding: 14px 32px !important; font-weight: 700 !important; font-size: 1rem !important;
        letter-spacing: 1px !important; transition: all 0.2s !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #4d94f7 0%, #3b82f6 100%) !important;
        box-shadow: 0 0 20px rgba(59,130,246,0.3) !important; transform: translateY(-1px) !important;
    }

    [data-testid="stMetric"] {
        background: var(--bg-card) !important; border: 1px solid var(--border) !important;
        border-radius: 8px !important; padding: 16px !important; text-align: center !important;
    }
    [data-testid="stMetric"] label { color: var(--text-muted) !important; font-size: 0.7rem !important; letter-spacing: 0.5px !important; }
    [data-testid="stMetric"] div[data-testid="stMetricValue"] { color: var(--text) !important; font-size: 1.3rem !important; font-weight: 800 !important; }

    [data-testid="stDataFrame"] { border: 1px solid var(--border) !important; border-radius: 8px !important; overflow: hidden !important; }
    [data-testid="stDataFrame"] th { background: var(--bg-elevated) !important; color: var(--text-dim) !important; font-size: 0.75rem !important; padding: 10px !important; }
    [data-testid="stDataFrame"] td { background: var(--bg-card) !important; color: var(--text) !important; font-size: 0.8rem !important; padding: 8px 10px !important; }

    div[data-testid="stAlert"] { background: var(--bg-card) !important; border-radius: 8px !important; border: 1px solid var(--border) !important; }
    div[data-testid="stAlert"] p, div[data-testid="stAlert"] span { color: var(--text) !important; }
    hr { border-color: var(--border) !important; }
    .stChart { background: transparent !important; }

    /* === 自定义 === */
    .market-card {
        background: linear-gradient(160deg, #0f1e38 0%, #091525 100%);
        border: 1px solid #223d60; border-radius: 10px; padding: 20px 24px; margin: 12px 0;
    }
    .market-card.hot { border-color: var(--red); box-shadow: 0 0 25px rgba(229,57,53,0.1); }

    .stock-card {
        background: var(--bg-card); border: 1px solid var(--border);
        border-radius: 10px; padding: 0; margin: 10px 0; overflow: hidden;
    }
    .stock-card.theme { border-left: 3px solid var(--blue); }
    .stock-card.main { border-left: 3px solid var(--red); }

    .stock-header {
        padding: 18px 22px; display: flex; justify-content: space-between; align-items: flex-start;
        border-bottom: 1px solid rgba(255,255,255,0.05);
    }
    .stock-body { padding: 18px 22px; }

    .tag {
        display: inline-block; padding: 3px 10px; border-radius: 4px;
        font-size: 0.72rem; font-weight: 600; margin: 1px 4px; letter-spacing: 0.3px;
    }
    .tag-red { background: rgba(229,57,53,0.18); color: var(--red-light); }
    .tag-blue { background: rgba(59,130,246,0.18); color: var(--blue-light); }
    .tag-gold { background: rgba(230,180,34,0.15); color: var(--gold-light); }
    .tag-green { background: rgba(16,185,129,0.15); color: #6ee7b7; }

    .theme-pill {
        display: inline-block; padding: 6px 14px; border-radius: 4px;
        font-size: 0.8rem; font-weight: 600; margin: 2px;
        background: rgba(59,130,246,0.15); color: var(--blue-light); border: 1px solid rgba(59,130,246,0.3);
    }

    .section-title {
        font-size: 0.82rem; font-weight: 700; color: var(--text-dim);
        letter-spacing: 2px; margin: 20px 0 10px 0;
    }

    .price-row { display: flex; gap: 36px; flex-wrap: wrap; align-items: flex-end; }
    .price-item { text-align: left; }
    .price-item .label { font-size: 0.7rem; color: var(--text-muted); letter-spacing: 0.5px; margin-bottom: 3px; }
    .price-item .value { font-size: 1.1rem; font-weight: 700; color: var(--text); }
    .price-item .sub { font-size: 0.74rem; margin-top: 2px; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 数据加载
# ============================================================
@st.cache_data(ttl=600, show_spinner="正在获取A股实时数据...")
def load_data():
    from data.fetcher import fetcher
    r = {'market': None, 'index': None, 'overview': {}, 'time': ''}
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

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_stock_chart(code, days=30):
    try:
        from data.fetcher import fetcher
        end = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=days + 5)).strftime('%Y%m%d')
        df = fetcher.get_daily_kline(code, start_date=start, end_date=end)
        if df is not None and not df.empty:
            return df[['date', 'close', 'volume']].tail(days)
    except Exception:
        pass
    return None

if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.market_data = None
    st.session_state.index_data = None
    st.session_state.overview = {}

# ============================================================
# 策略
# ============================================================
STRATEGY_NAMES = {
    'mean_reversion': '超跌反弹',
    'trend_momentum': '趋势动量',
    'pb_roe': 'PB-ROE价值',
}

def run_core_strategies(market_data):
    from strategies.pb_roe import PBROEStrategy
    from strategies.trend_momentum import TrendMomentumStrategy
    from strategies.mean_reversion import MeanReversionStrategy
    from config import DEFAULT_STRATEGY_PARAMS

    strategies = [
        ('mean_reversion', MeanReversionStrategy(DEFAULT_STRATEGY_PARAMS.get('mean_reversion'))),
        ('trend_momentum', TrendMomentumStrategy(DEFAULT_STRATEGY_PARAMS.get('trend_momentum'))),
        ('pb_roe', PBROEStrategy(DEFAULT_STRATEGY_PARAMS.get('pb_roe'))),
    ]
    all_signals = []
    for key, s in strategies:
        try:
            s.set_market_data(market_data)
            result = s.run()
            for sig in result.signals:
                sig.strategy = STRATEGY_NAMES[key]
                sig.factors['strategy_key'] = key
                sig.factors['strategy_name'] = STRATEGY_NAMES[key]
            all_signals.extend(result.signals)
        except Exception:
            pass

    merged = {}
    for sig in all_signals:
        if sig.code not in merged:
            merged[sig.code] = sig
        else:
            merged[sig.code].confidence = min(95, merged[sig.code].confidence + 8)
            merged[sig.code].factors['consensus'] = merged[sig.code].factors.get('consensus', 1) + 1
    return sorted(merged.values(), key=lambda x: x.confidence, reverse=True)

# ============================================================
# 主界面
# ============================================================
st.markdown("""
<div style="padding:8px 0 4px 0">
    <span style="font-size:1.2rem;font-weight:800;color:#f8f9fc;letter-spacing:1px">A股量化选股</span>
    <span style="color:#8a92a4;font-size:0.72rem;margin-left:10px">温度计 · 板块 · 精选</span>
</div>
""", unsafe_allow_html=True)

t1, t2, t3 = st.tabs(["早盘扫描", "大盘数据", "使用说明"])

# ============================================================
# Tab 1
# ============================================================
with t1:
    c1, c2 = st.columns([2, 1])
    with c1:
        total_capital = st.number_input("总资金（元）", min_value=10000, value=100000, step=10000)
    with c2:
        risk_level = st.selectbox("风险偏好",
            ['conservative', 'moderate', 'aggressive'],
            format_func=lambda x: {'conservative': '保守', 'moderate': '稳健', 'aggressive': '激进'}[x], index=1)

    need_load = not st.session_state.data_loaded

    if st.button("开始扫描", type="primary", use_container_width=True):
        if need_load:
            with st.spinner("正在获取全市场实时数据..."):
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
            st.error("数据获取失败，请检查网络后重试")
        else:
            dq = market_df['_data_quality'].iloc[0] if '_data_quality' in market_df.columns else 'unknown'

            # Layer 1: 市场温度计
            from market.market_regime import regime_detector
            regime = regime_detector.detect(market_df)

            # Layer 2: 板块轮动
            from market.sector_rotation import sector_analyzer
            sector_result = sector_analyzer.analyze(market_df)

            # ---------- 市场温度计 ----------
            card_class = 'market-card hot' if regime.score >= 70 else 'market-card'
            fg_color = '#ff8a80' if regime.fear_greed_index > 70 else ('#6ee7b7' if regime.fear_greed_index < 30 else '#ffd54f')
            st.markdown(f"""
            <div class="{card_class}">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px">
                    <div>
                        <div style="font-size:1.4rem;font-weight:800;color:#f8f9fc">{regime.status_emoji} {regime.status}</div>
                        <div style="color:#8a92a4;font-size:0.75rem;margin-top:2px">评分 {regime.score}/100</div>
                    </div>
                    <div style="display:flex;gap:28px;flex-wrap:wrap">
                        <div style="text-align:center"><div style="color:#8a92a4;font-size:0.65rem">涨跌比</div><div style="font-size:1.05rem;font-weight:700;color:#f8f9fc">{regime.breadth}%</div></div>
                        <div style="text-align:center"><div style="color:#8a92a4;font-size:0.65rem">涨停</div><div style="font-size:1.05rem;font-weight:700;color:#ff8a80">{regime.limit_up_count}</div></div>
                        <div style="text-align:center"><div style="color:#8a92a4;font-size:0.65rem">跌停</div><div style="font-size:1.05rem;font-weight:700;color:#6ee7b7">{regime.limit_down_count}</div></div>
                        <div style="text-align:center"><div style="color:#8a92a4;font-size:0.65rem">成交额</div><div style="font-size:1.05rem;font-weight:700;color:#f8f9fc">{regime.total_amount:.0f}亿</div></div>
                        <div style="text-align:center"><div style="color:#8a92a4;font-size:0.65rem">贪婪指数</div><div style="font-size:1.05rem;font-weight:700;color:{fg_color}">{regime.fear_greed_index}/100</div></div>
                    </div>
                </div>
                <div style="margin-top:14px;padding:8px 14px;background:rgba(59,130,246,0.06);border-radius:6px;font-size:0.8rem;color:#c0c6d4">
                    建议仓位 <strong style="color:#ffd54f">{regime.suggested_position*100:.0f}%</strong> &nbsp;·&nbsp; {' &nbsp;·&nbsp; '.join(regime.advice)}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ---------- 主线板块 ----------
            if sector_result.main_themes:
                pills = ' '.join(f'<span class="theme-pill">{s.name} <span style="color:#ffd54f">{s.pct_change:+.1f}%</span></span>' for s in sector_result.main_themes[:8])
                st.markdown(f'<div style="margin:8px 0"><span style="color:#8a92a4;font-weight:600;font-size:0.8rem;margin-right:8px">主线</span>{pills}</div>', unsafe_allow_html=True)

            if sector_result.ai_tech_sectors:
                pills = ' '.join(f'<span class="tag tag-blue">{s.name}</span>' for s in sector_result.ai_tech_sectors[:6])
                st.markdown(f'<div style="margin:4px 0"><span style="color:#b4d4ff;font-weight:600;font-size:0.75rem;margin-right:8px">AI / 科技</span>{pills}</div>', unsafe_allow_html=True)

            if dq == 'basic':
                st.caption("当前仅价量数据。交易时段通常自动获取完整数据。")

            # Layer 3: 策略扫描
            with st.spinner("正在运行策略分析..."):
                signals = run_core_strategies(market_df)

            if not signals:
                st.warning(f"当前{regime.status}，无符合条件的买入信号")
            else:
                position_multiplier = {'conservative': 0.7, 'moderate': 1.0, 'aggressive': 1.3}.get(risk_level, 1.0)
                effective_capital = total_capital * regime.suggested_position * position_multiplier

                from portfolio.allocator import PortfolioAllocator
                allocator = PortfolioAllocator(total_capital=effective_capital)
                plan = allocator.allocate(signals, risk_level=risk_level)

                main_theme_codes = set(sector_result.hot_stocks) if sector_result.hot_stocks else set()

                st.markdown(f'<div class="section-title">精选结果 &nbsp;·&nbsp; {len(signals)} 信号 &nbsp;→&nbsp; {len(plan.allocations)} 入选</div>', unsafe_allow_html=True)

                # ---------- 个股卡片 ----------
                if plan.allocations:
                    for i, a in enumerate(plan.allocations, 1):
                        s = a.stock
                        loss_amt = a.shares * (s.price - s.stop_loss)
                        profit_amt = a.shares * (s.stop_profit - s.price)
                        strat_count = s.factors.get('consensus', 1)
                        in_theme = s.code in main_theme_codes
                        card_class = 'stock-card main' if in_theme else 'stock-card'
                        strategy_name = s.factors.get('strategy_name', s.strategy)

                        chart_df = fetch_stock_chart(s.code, days=30)

                        # 卡片头
                        st.markdown(f"""
                        <div class="{card_class}">
                            <div class="stock-header">
                                <div>
                                    <span style="font-size:1.15rem;font-weight:700;color:#f8f9fc">#{i} {s.name}</span>
                                    <span class="tag tag-gold" style="margin-left:8px">{s.confidence:.0f}%</span>
                                    <span class="tag tag-blue">{strategy_name}</span>
                                    {f'<span class="tag tag-green">多策略共识</span>' if strat_count >= 2 else ''}
                                    {f'<span class="tag tag-red">主线板块</span>' if in_theme else ''}
                                </div>
                            </div>
                            <div class="stock-body">
                                <div class="price-row">
                                    <div class="price-item">
                                        <div class="label">买入价</div>
                                        <div class="value" style="color:#ffd54f">¥{s.price}</div>
                                    </div>
                                    <div class="price-item">
                                        <div class="label">数量</div>
                                        <div class="value">{(a.shares//100)}手</div>
                                        <div class="sub" style="color:#8a92a4">{a.shares}股</div>
                                    </div>
                                    <div class="price-item">
                                        <div class="label">金额</div>
                                        <div class="value" style="color:#b4d4ff">¥{a.amount:,.0f}</div>
                                        <div class="sub" style="color:#8a92a4">仓位 {a.weight}%</div>
                                    </div>
                                    <div class="price-item">
                                        <div class="label">止损</div>
                                        <div class="value" style="color:#ff8a80">¥{s.stop_loss}</div>
                                        <div class="sub" style="color:#ff8a80">-¥{loss_amt:,.0f}</div>
                                    </div>
                                    <div class="price-item">
                                        <div class="label">止盈</div>
                                        <div class="value" style="color:#6ee7b7">¥{s.stop_profit}</div>
                                        <div class="sub" style="color:#6ee7b7">+¥{profit_amt:,.0f}</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                        # 走势图
                        if chart_df is not None and len(chart_df) >= 5:
                            with st.expander(f"{s.name} 近30日走势", expanded=(i == 1)):
                                first_close = chart_df['close'].iloc[0]
                                last_close = chart_df['close'].iloc[-1]
                                trend_color = '#ff8a80' if last_close >= first_close else '#3b82f6'
                                chart_df_display = chart_df.set_index('date')
                                st.line_chart(chart_df_display['close'], height=180, color=trend_color, use_container_width=True)
                                st.bar_chart(chart_df_display['volume'], height=60, color='#8a92a4', use_container_width=True)
                        else:
                            st.caption(f"{s.name} 走势数据暂不可用")

                        # 理由
                        st.markdown(f"""
                        <div style="margin:-4px 0 0 0;padding:8px 22px;font-size:0.8rem;color:#c0c6d4">
                            {a.reason}
                        </div>
                        """, unsafe_allow_html=True)

                # ---------- 资金总览 ----------
                st.markdown('<div class="section-title">资金总览</div>', unsafe_allow_html=True)
                c1, c2, c3, c4 = st.columns(4)
                used_pct = plan.used_capital / total_capital * 100 if total_capital > 0 else 0
                actual_cash = total_capital - plan.used_capital if total_capital > plan.used_capital else 0
                cash_pct = actual_cash / total_capital * 100 if total_capital > 0 else 0

                c1.metric("总资金", f"¥{total_capital:,.0f}",
                          f"有效 ¥{effective_capital:,.0f}" if abs(effective_capital - total_capital) > 100 else None)
                c2.metric("已使用", f"¥{plan.used_capital:,.0f}", f"{used_pct:.0f}%")
                c3.metric("预留现金", f"¥{actual_cash:,.0f}", f"{cash_pct:.0f}%")
                risk_label = "分散" if plan.risk_score < 30 else ("适中" if plan.risk_score < 50 else "集中")
                c4.metric("组合风险", f"{plan.risk_score}/100", risk_label, delta_color="off")

                if plan.notes:
                    for note in plan.notes:
                        st.caption(f"— {note}")

                # ---------- 未入选 ----------
                allocated_codes = {a.stock.code for a in plan.allocations}
                remaining = [s for s in signals if s.code not in allocated_codes and s.confidence >= 65]
                if remaining:
                    with st.expander(f"其他未入选信号（{len(remaining)}个）"):
                        for s in remaining[:8]:
                            sn = s.factors.get('strategy_name', s.strategy)
                            st.markdown(f"""
                            <div style="padding:6px 12px;margin:3px 0;background:rgba(255,255,255,0.02);border-radius:6px;font-size:0.8rem">
                                <strong style="color:#f8f9fc">{s.name}</strong>
                                <span style="color:#ffd54f;margin-left:6px">{s.confidence:.0f}%</span>
                                <span class="tag tag-blue" style="margin-left:6px">{sn}</span>
                                <span style="color:#8a92a4;margin-left:8px">¥{s.price} &nbsp; 止损 ¥{s.stop_loss}</span>
                            </div>
                            """, unsafe_allow_html=True)

        if not need_load:
            st.divider()
            if st.button("刷新数据重新扫描"):
                st.session_state.data_loaded = False
                st.cache_data.clear()
                st.rerun()

    if st.session_state.data_loaded:
        n = len(st.session_state.market_data) if st.session_state.market_data is not None else 0
        st.caption(f"数据已就绪（{n}只股票），点击上方按钮开始扫描")

# ============================================================
# Tab 2
# ============================================================
with t2:
    st.markdown('<div class="section-title">市场数据</div>', unsafe_allow_html=True)
    if not st.session_state.data_loaded:
        st.info("请先在「早盘扫描」页加载市场数据")
    else:
        df = st.session_state.market_data
        if df is not None and not df.empty:
            st.caption(f"{len(df)}只股票 | 更新于 {st.session_state.get('market_time', '')}")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**涨幅榜 Top 15**")
                dc = ['name', 'price', 'pct_change'] if all(c in df.columns for c in ['name', 'price', 'pct_change']) else None
                if dc:
                    top = df.nlargest(15, 'pct_change')[dc].copy()
                    top.columns = ['名称', '价格', '涨幅%']
                    st.dataframe(top, hide_index=True, use_container_width=True)
            with col_b:
                st.markdown("**跌幅榜 Top 15**")
                if dc:
                    bot = df.nsmallest(15, 'pct_change')[dc].copy()
                    bot.columns = ['名称', '价格', '涨幅%']
                    st.dataframe(bot, hide_index=True, use_container_width=True)

            if 'pct_change' in df.columns:
                bins = [-100, -9.9, -5, -3, -1, 0, 1, 3, 5, 9.9, 100]
                labels = ['跌停', '-5~-10', '-3~-5', '-1~-3', '0~-1', '0~+1', '+1~3', '+3~5', '+5~10', '涨停']
                df_c = df.copy()
                df_c['rng'] = pd.cut(df_c['pct_change'], bins=bins, labels=labels)
                dist = df_c['rng'].value_counts().reindex(labels, fill_value=0)
                st.bar_chart(pd.DataFrame({'区间': labels, '数量': dist.values}).set_index('区间'), use_container_width=True)

# ============================================================
# Tab 3
# ============================================================
with t3:
    st.markdown("""
    <div style="max-width:700px;color:#c0c6d4">

    ### 操作流程

    **开盘后打开系统** → 点「开始扫描」 → 查看精选结果 → 在券商APP设条件单 → 关系统

    ### 三层决策

    | 层级 | 作用 | 输出 |
    |------|------|------|
    | 市场温度计 | 判断牛熊 | 建议仓位 |
    | 板块轮动 | 识别主线 | 热门板块 |
    | 个股精选 | 选最优标的 | 买入价 / 数量 / 止损止盈 |

    ### 三大策略

    | 策略 | 逻辑 | 周期 | 风险 |
    |------|------|------|------|
    | 超跌反弹 | 超跌缩量 → 反弹就走 | 1-5天 | 低 |
    | 趋势动量 | 多头排列 + 放量 → 顺势 | 3-10天 | 中 |
    | PB-ROE价值 | 低估好公司 → 安全边际 | 中长期 | 低 |

    ### 原则
    - 每天最多2-4只，不贪多
    - 止损必须设，亏了就认
    - 市场不好时空仓
    - 别人贪婪时主动降仓
    </div>
    """, unsafe_allow_html=True)
