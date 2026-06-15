"""
A股量化选股系统 — 三层体系：市场温度计 → 板块轮动 → 个股精选
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

# ============================================================
# 全局暗色主题 — 覆盖所有Streamlit白底
# ============================================================
st.markdown("""
<style>
    /* === 根变量 === */
    :root {
        --bg-primary: #0a0e17;
        --bg-secondary: #111827;
        --bg-card: #141c2b;
        --bg-elevated: #1a2332;
        --border: #1e2d3d;
        --border-active: #3b82f6;
        --text-primary: #e2e8f0;
        --text-secondary: #94a3b8;
        --text-muted: #64748b;
        --accent: #3b82f6;
        --accent-glow: #60a5fa;
        --gold: #f59e0b;
        --green: #10b981;
        --red: #ef4444;
        --purple: #8b5cf6;
    }

    /* === 全局底色 === */
    .stApp { background: var(--bg-primary) !important; }
    .main { background: var(--bg-primary) !important; }
    section[data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }
    #MainMenu, footer, header { display: none !important; }

    /* === 消除所有白底 === */
    div[data-baseweb="select"] > div,
    div[data-baseweb="popover"] { background: var(--bg-elevated) !important; border-color: var(--border) !important; }
    input, textarea, .stTextInput input, .stNumberInput input,
    [data-baseweb="input"] input, [data-baseweb="input"] > div {
        background: var(--bg-elevated) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
    }
    .stSelectbox > div > div { background: var(--bg-elevated) !important; border-color: var(--border) !important; }
    div[data-baseweb="select"] span, div[data-baseweb="popover"] span { color: var(--text-primary) !important; }
    ul[data-baseweb="menu"], li[data-baseweb="option"] { background: var(--bg-elevated) !important; color: var(--text-primary) !important; }
    li[data-baseweb="option"]:hover { background: var(--accent) !important; }

    /* === Expander === */
    .streamlit-expanderHeader { background: var(--bg-card) !important; border: 1px solid var(--border) !important;
        border-radius: 10px !important; color: var(--text-primary) !important; font-weight: 600 !important; }
    .streamlit-expanderContent { background: var(--bg-secondary) !important; border: 1px solid var(--border) !important;
        border-top: none !important; border-radius: 0 0 10px 10px !important; padding: 16px !important; }

    /* === Tab Bar === */
    .stTabs [data-baseweb="tab"] {
        background: var(--bg-card) !important; color: var(--text-secondary) !important;
        border-radius: 10px 10px 0 0 !important; padding: 10px 18px !important;
        font-weight: 600 !important; border: 1px solid var(--border) !important; border-bottom: none !important;
        margin-right: 2px !important;
    }
    .stTabs [aria-selected="true"] {
        background: var(--accent) !important; color: white !important; border-color: var(--accent) !important;
    }

    /* === 按钮 === */
    .stButton > button {
        background: var(--accent) !important; color: white !important; border: none !important;
        border-radius: 10px !important; padding: 12px 28px !important; font-weight: 700 !important;
        font-size: 0.95rem !important; transition: all 0.2s !important; letter-spacing: 0.3px !important;
    }
    .stButton > button:hover { background: #2563eb !important; transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(59,130,246,0.3) !important; }

    /* === Metric === */
    [data-testid="stMetric"] {
        background: var(--bg-card) !important; border: 1px solid var(--border) !important;
        border-radius: 10px !important; padding: 14px !important;
        text-align: center !important;
    }
    [data-testid="stMetric"] label { color: var(--text-muted) !important; font-size: 0.7rem !important;
        text-transform: uppercase !important; letter-spacing: 0.5px !important; }
    [data-testid="stMetric"] div[data-testid="stMetricValue"] { color: var(--text-primary) !important;
        font-size: 1.4rem !important; font-weight: 800 !important; }
    [data-testid="stMetric"] div[data-testid="stMetricDelta"] { font-size: 0.85rem !important; }

    /* === DataFrame === */
    [data-testid="stDataFrame"] { border: 1px solid var(--border) !important; border-radius: 10px !important;
        overflow: hidden !important; }
    [data-testid="stDataFrame"] th { background: var(--bg-elevated) !important; color: var(--text-secondary) !important;
        font-size: 0.75rem !important; font-weight: 600 !important; padding: 10px !important; }
    [data-testid="stDataFrame"] td { background: var(--bg-card) !important; color: var(--text-primary) !important;
        font-size: 0.8rem !important; padding: 8px 10px !important; }

    /* === 自定义卡片 === */
    .market-card {
        background: linear-gradient(135deg, #141c2b 0%, #1a2332 100%);
        border: 1px solid var(--border); border-radius: 14px;
        padding: 20px 24px; margin: 12px 0;
    }
    .market-card-alt { border-color: var(--accent); box-shadow: 0 0 20px rgba(59,130,246,0.08); }
    .stock-card {
        background: var(--bg-card); border: 1px solid var(--border);
        border-radius: 12px; padding: 18px 20px; margin: 10px 0;
        transition: border-color 0.2s;
    }
    .stock-card:hover { border-color: var(--accent); }
    .stock-card.theme { border-left: 3px solid var(--purple); }
    .stock-card.normal { border-left: 3px solid var(--accent); }

    .tag {
        display: inline-block; padding: 3px 8px; border-radius: 6px;
        font-size: 0.7rem; font-weight: 600; margin: 1px 3px;
    }
    .tag-blue { background: #1e3a5f; color: #93c5fd; }
    .tag-gold { background: #3d2e0a; color: #fbbf24; }
    .tag-green { background: #0a3d24; color: #6ee7b7; }
    .tag-purple { background: #2d1f5e; color: #c4b5fd; }
    .tag-red { background: #3d0a0a; color: #fca5a5; }

    .theme-pill {
        display: inline-block; padding: 6px 14px; border-radius: 20px;
        font-size: 0.78rem; font-weight: 600; margin: 2px;
        background: #1e3a5f; color: #93c5fd; border: 1px solid #2563eb;
    }

    .section-title {
        font-size: 0.9rem; font-weight: 700; color: var(--text-secondary);
        text-transform: uppercase; letter-spacing: 1px; margin: 16px 0 8px 0;
    }

    /* === Alert / Info / Warning === */
    div[data-testid="stAlert"] {
        background: var(--bg-card) !important; border-radius: 10px !important;
        border: 1px solid var(--border) !important;
    }
    .stAlert { background: var(--bg-card) !important; color: var(--text-primary) !important; }

    /* === Chart === */
    .stChart { background: var(--bg-card) !important; border-radius: 10px !important;
        border: 1px solid var(--border) !important; padding: 10px !important; }

    /* === Spinner === */
    .stSpinner > div { border-color: var(--accent) !important; }

    /* === Divider === */
    hr { border-color: var(--border) !important; }
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

if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.market_data = None
    st.session_state.index_data = None
    st.session_state.overview = {}

# ============================================================
# 三大核心策略
# ============================================================
CORE_STRATEGIES = {
    'mean_reversion': {
        'name': '超跌反弹',
        'emoji': '📉',
        'desc': '严重超跌后缩量止跌，反弹3-5%就走，单笔止损-3%',
        'why': '快进快出，胜率高，不扛单，适合积小胜',
        'backtest': '完整回测',
        'risk': '低风险',
    },
    'trend_momentum': {
        'name': '趋势动量',
        'emoji': '🚀',
        'desc': '均线多头排列 + 放量突破，顺势而为，持有3-10天',
        'why': 'A股趋势效应强，顺势比抄底更稳',
        'backtest': '完整回测',
        'risk': '中风险',
    },
    'pb_roe': {
        'name': 'PB-ROE价值',
        'emoji': '💎',
        'desc': '低PB+合理PE的价值洼地，安全边际高，适合底仓',
        'why': '低估好公司，防守型配置，对冲短期波动',
        'backtest': '部分回测',
        'risk': '低风险',
    },
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
                sig.strategy = CORE_STRATEGIES[key]['name']
                sig.factors['strategy_key'] = key
                sig.factors['strategy_emoji'] = CORE_STRATEGIES[key]['emoji']
                sig.factors['strategy_why'] = CORE_STRATEGIES[key]['why']
                sig.factors['backtest_level'] = CORE_STRATEGIES[key]['backtest']
                sig.factors['risk_level'] = CORE_STRATEGIES[key]['risk']
            all_signals.extend(result.signals)
        except Exception:
            pass

    merged = {}
    for sig in all_signals:
        if sig.code not in merged:
            merged[sig.code] = sig
        else:
            merged[sig.code].confidence = min(95, merged[sig.code].confidence + 8)
            if sig.strategy not in merged[sig.code].reason:
                merged[sig.code].reason += f' | +{sig.strategy}'
            merged[sig.code].factors['consensus'] = merged[sig.code].factors.get('consensus', 1) + 1

    return sorted(merged.values(), key=lambda x: x.confidence, reverse=True)

# ============================================================
# 主界面
# ============================================================
st.markdown("""
<div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0">
    <div>
        <span style="font-size:1.3rem;font-weight:800;color:#f0f0f0">A股量化选股</span>
        <span style="color:#64748b;font-size:0.75rem;margin-left:10px;font-weight:400">市场温度计 · 板块轮动 · 智能精选</span>
    </div>
</div>
""", unsafe_allow_html=True)

t1, t2, t3 = st.tabs(["早盘扫描", "大盘数据", "使用说明"])

# ============================================================
# Tab 1: 早盘扫描
# ============================================================
with t1:
    c1, c2 = st.columns([2, 1])
    with c1:
        total_capital = st.number_input("总资金（元）", min_value=10000, value=100000, step=10000,
                                        help="你的实际可用资金总额")
    with c2:
        risk_level = st.selectbox("风险偏好",
            ['conservative', 'moderate', 'aggressive'],
            format_func=lambda x: {'conservative': '保守', 'moderate': '稳健', 'aggressive': '激进'}[x],
            index=1)

    need_load = not st.session_state.data_loaded
    btn_label = "开始扫描" if need_load else "开始扫描"
    btn_help = "含数据加载，约50秒" if need_load else "数据已就绪，约15秒"

    if st.button(btn_label, type="primary", use_container_width=True, help=btn_help):
        # --- 加载数据 ---
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

            # ====== Layer 1: 市场温度计 ======
            from market.market_regime import regime_detector
            regime = regime_detector.detect(market_df)

            # ====== Layer 2: 板块轮动 ======
            from market.sector_rotation import sector_analyzer
            sector_result = sector_analyzer.analyze(market_df)

            # ---------- 市场温度计卡片 ----------
            fg_color = '#ef4444' if regime.fear_greed_index > 70 else ('#10b981' if regime.fear_greed_index < 30 else '#f59e0b')
            st.markdown(f"""
            <div class="market-card market-card-alt">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px">
                    <div>
                        <div style="font-size:1.5rem;font-weight:800;color:#f0f0f0">{regime.status_emoji} {regime.status}</div>
                        <div style="color:#64748b;font-size:0.8rem;margin-top:4px">市场温度计评分 {regime.score}/100</div>
                    </div>
                    <div style="display:flex;gap:24px;flex-wrap:wrap">
                        <div style="text-align:center"><div style="color:#64748b;font-size:0.65rem;text-transform:uppercase">涨跌比</div><div style="font-size:1.1rem;font-weight:700;color:#f0f0f0">{regime.breadth}%</div></div>
                        <div style="text-align:center"><div style="color:#64748b;font-size:0.65rem;text-transform:uppercase">涨停</div><div style="font-size:1.1rem;font-weight:700;color:#ef4444">{regime.limit_up_count}</div></div>
                        <div style="text-align:center"><div style="color:#64748b;font-size:0.65rem;text-transform:uppercase">跌停</div><div style="font-size:1.1rem;font-weight:700;color:#10b981">{regime.limit_down_count}</div></div>
                        <div style="text-align:center"><div style="color:#64748b;font-size:0.65rem;text-transform:uppercase">成交额</div><div style="font-size:1.1rem;font-weight:700;color:#f0f0f0">{regime.total_amount:.0f}亿</div></div>
                        <div style="text-align:center"><div style="color:#64748b;font-size:0.65rem;text-transform:uppercase">恐惧贪婪</div><div style="font-size:1.1rem;font-weight:700;color:{fg_color}">{regime.fear_greed_index}/100</div></div>
                    </div>
                </div>
                <div style="margin-top:12px;padding:8px 14px;background:rgba(59,130,246,0.08);border-radius:8px;font-size:0.82rem;color:#94a3b8">
                    建议仓位 <strong style="color:#fbbf24">{regime.suggested_position*100:.0f}%</strong> &nbsp;|&nbsp; {' &nbsp;|&nbsp; '.join(regime.advice)}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ---------- 主线板块 ----------
            if sector_result.main_themes:
                pills = ' '.join(f'<span class="theme-pill">{s.name} <span style="color:#fbbf24">{s.pct_change:+.1f}%</span></span>' for s in sector_result.main_themes[:8])
                st.markdown(f'<div style="margin:8px 0;font-size:0.85rem"><span style="color:#64748b;font-weight:600;margin-right:8px">主线板块</span>{pills}</div>', unsafe_allow_html=True)

            if sector_result.ai_tech_sectors:
                pills = ' '.join(f'<span class="tag tag-purple">{s.name}</span>' for s in sector_result.ai_tech_sectors[:6])
                st.markdown(f'<div style="margin:6px 0;font-size:0.8rem"><span style="color:#8b5cf6;font-weight:600;margin-right:8px">AI / 科技</span>{pills}</div>', unsafe_allow_html=True)

            if dq == 'basic':
                st.caption("当前使用新浪数据源（仅价量）。趋势动量可用，超跌反弹为估算值。交易时段通常自动切换至东方财富。")

            # ====== Layer 3: 策略扫描 ======
            with st.spinner("正在运行3大核心策略..."):
                signals = run_core_strategies(market_df)

            if not signals:
                st.warning(f"当前{regime.status}，无符合条件的买入信号。空仓也是策略。")
                if regime.sentiment == 'fearful':
                    st.info("市场冰点，别人恐惧我贪婪——可小仓位关注超跌标的。")
            else:
                # 动态仓位
                position_multiplier = {'conservative': 0.7, 'moderate': 1.0, 'aggressive': 1.3}.get(risk_level, 1.0)
                effective_capital = total_capital * regime.suggested_position * position_multiplier

                from portfolio.allocator import PortfolioAllocator
                allocator = PortfolioAllocator(total_capital=effective_capital)
                plan = allocator.allocate(signals, risk_level=risk_level)

                main_theme_codes = set(sector_result.hot_stocks) if sector_result.hot_stocks else set()

                st.markdown(f'<div class="section-title">精选结果 &nbsp;·&nbsp; {len(signals)}个信号 → {len(plan.allocations)}只入选</div>', unsafe_allow_html=True)

                # ---------- 股票卡片 ----------
                if plan.allocations:
                    for i, a in enumerate(plan.allocations, 1):
                        s = a.stock
                        loss_amount = a.shares * (s.price - s.stop_loss)
                        profit_amount = a.shares * (s.stop_profit - s.price)
                        strategy_count = s.reason.count('|') + 1
                        in_theme = s.code in main_theme_codes
                        card_class = 'stock-card theme' if in_theme else 'stock-card normal'
                        emoji = s.factors.get('strategy_emoji', '')
                        risk = s.factors.get('risk_level', '')
                        risk_tag = 'tag-red' if '高' in risk else ('tag-gold' if '中' in risk else 'tag-green')

                        st.markdown(f"""
                        <div class="{card_class}">
                            <div style="display:flex;justify-content:space-between;align-items:flex-start">
                                <div>
                                    <span style="font-size:1.1rem;font-weight:700;color:#f0f0f0">#{i} {s.name}</span>
                                    <span class="tag tag-gold" style="margin-left:8px">{s.confidence:.0f}%</span>
                                    <span class="tag tag-blue" style="margin-left:4px">{emoji} {s.strategy}</span>
                                    <span class="tag {risk_tag}">{risk}</span>
                                    {f'<span class="tag tag-purple">主线板块</span>' if in_theme else ''}
                                    {f'<span class="tag tag-green">{strategy_count}策略共识</span>' if strategy_count >= 2 else ''}
                                </div>
                            </div>
                            <div style="display:flex;gap:28px;margin-top:14px;flex-wrap:wrap">
                                <div><span style="color:#64748b;font-size:0.7rem">买入价</span><br><span style="font-size:1rem;font-weight:700;color:#fbbf24">¥{s.price}</span></div>
                                <div><span style="color:#64748b;font-size:0.7rem">数量</span><br><span style="font-size:1rem;font-weight:700;color:#f0f0f0">{a.shares}股 <span style="font-size:0.75rem;color:#64748b">({a.shares//100}手)</span></span></div>
                                <div><span style="color:#64748b;font-size:0.7rem">金额</span><br><span style="font-size:1rem;font-weight:700;color:#60a5fa">¥{a.amount:,.0f} <span style="font-size:0.75rem;color:#64748b">({a.weight}%)</span></span></div>
                                <div><span style="color:#64748b;font-size:0.7rem">止损</span><br><span style="font-size:1rem;font-weight:700;color:#ef4444">¥{s.stop_loss}</span><br><span style="font-size:0.7rem;color:#ef4444">-¥{loss_amount:,.0f}</span></div>
                                <div><span style="color:#64748b;font-size:0.7rem">止盈</span><br><span style="font-size:1rem;font-weight:700;color:#10b981">¥{s.stop_profit}</span><br><span style="font-size:0.7rem;color:#10b981">+¥{profit_amount:,.0f}</span></div>
                            </div>
                            <div style="margin-top:12px;padding:8px 12px;background:rgba(245,158,11,0.06);border-radius:8px;font-size:0.8rem;color:#fbbf24">
                                {a.reason}
                            </div>
                            <div style="margin-top:6px;font-size:0.72rem;color:#64748b">{a.rank_info}</div>
                        </div>
                        """, unsafe_allow_html=True)

                # ---------- 资金总览（修复版）----------
                st.markdown('<div class="section-title">资金总览</div>', unsafe_allow_html=True)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("总资金", f"¥{total_capital:,.0f}",
                          f"有效 ¥{effective_capital:,.0f}" if effective_capital != total_capital else None)
                c2.metric("已使用", f"¥{plan.used_capital:,.0f}",
                          f"{plan.used_capital/total_capital*100:.0f}% 总资金")
                # 实际预留 = 总资金 - 已使用（包含了市场建议的现金缓冲）
                actual_cash = total_capital - plan.used_capital
                c3.metric("预留现金", f"¥{actual_cash:,.0f}",
                          f"{actual_cash/total_capital*100:.0f}%")
                c4.metric("组合风险", f"{plan.risk_score}/100",
                          "低集中度" if plan.risk_score < 30 else ("适中" if plan.risk_score < 50 else "较集中"),
                          delta_color="off")

                if plan.notes:
                    for note in plan.notes:
                        st.caption(f"— {note}")

                # ---------- 其他信号 ----------
                allocated_codes = {a.stock.code for a in plan.allocations}
                remaining = [s for s in signals if s.code not in allocated_codes]
                strong_remaining = [s for s in remaining if s.confidence >= 70]
                if strong_remaining:
                    with st.expander(f"其他未入选信号（{len(remaining)}个，因仓位/分散化限制）"):
                        for s in strong_remaining[:8]:
                            emoji = s.factors.get('strategy_emoji', '')
                            st.markdown(f"""
                            <div style="padding:8px 12px;margin:4px 0;background:rgba(100,116,139,0.05);border-radius:8px;font-size:0.82rem">
                                <strong style="color:#f0f0f0">{s.name}</strong>
                                <span style="color:#f59e0b;margin-left:8px">{s.confidence:.0f}%</span>
                                <span style="color:#64748b;margin-left:4px">{emoji} {s.strategy}</span>
                                <span style="color:#94a3b8;margin-left:8px">买¥{s.price} 止¥{s.stop_loss} 盈¥{s.stop_profit}</span>
                            </div>
                            """, unsafe_allow_html=True)

        # 刷新按钮
        if not need_load:
            st.divider()
            if st.button("刷新数据重新扫描"):
                st.session_state.data_loaded = False
                st.cache_data.clear()
                st.rerun()

    # 未扫描提示
    if st.session_state.data_loaded and not st.session_state.get('_scanned', False):
        n = len(st.session_state.market_data) if st.session_state.market_data is not None else 0
        st.caption(f"数据已就绪（{n}只股票），点击上方按钮开始扫描")

# ============================================================
# Tab 2: 大盘数据
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
                labels = ['跌停', '-5~-10%', '-3~-5%', '-1~-3%', '0~-1%', '0~+1%', '+1~3%', '+3~5%', '+5~10%', '涨停']
                df_c = df.copy()
                df_c['rng'] = pd.cut(df_c['pct_change'], bins=bins, labels=labels)
                dist = df_c['rng'].value_counts().reindex(labels, fill_value=0)
                st.bar_chart(pd.DataFrame({'区间': labels, '数量': dist.values}).set_index('区间'), use_container_width=True)

# ============================================================
# Tab 3: 使用说明
# ============================================================
with t3:
    st.markdown("""
    <div style="max-width:700px">

    ### 操作流程

    **1. 开盘后打开系统** → 点「开始扫描」
    **2. 查看市场温度** → 了解当前是牛是熊
    **3. 查看精选结果** → 系统自动给出具体买入方案
    **4. 在券商APP设条件单** → 买入价、止损价、止盈价一键填入
    **5. 关掉系统** → 条件单会自动执行

    ### 三层决策体系

    | 层级 | 作用 | 输出 |
    |------|------|------|
    | 市场温度计 | 判断牛熊，决定仓位 | 建议仓位比例 |
    | 板块轮动 | 识别主线，找准方向 | 主线板块列表 |
    | 个股精选 | 板块内择优，控制风险 | 买入价+数量+止损止盈 |

    ### 三大核心策略

    | 策略 | 逻辑 | 持有周期 | 风险 |
    |------|------|---------|------|
    | 超跌反弹 | 跌多了就买，反弹就走 | 1-5天 | 低 |
    | 趋势动量 | 多头排列+放量，顺势而为 | 3-10天 | 中 |
    | PB-ROE价值 | 低估好公司，安全边际 | 中长期 | 低 |

    ### 核心原则

    - **每天最多2-4只**，不贪多
    - **止损必须设**，亏了就认
    - **市场不好时空仓**，不买也是赚钱
    - **别人贪婪我恐惧**，市场过热时主动降仓
    </div>
    """, unsafe_allow_html=True)
