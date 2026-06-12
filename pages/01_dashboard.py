"""
仪表盘 - 大盘概览、涨跌统计（使用共享缓存数据，秒加载）
"""
import streamlit as st
import pandas as pd
from datetime import datetime


def show():
    df = st.session_state.get('market_data')
    if df is None or df.empty:
        st.info("⏳ 数据正在加载中，请稍候...如果长时间未响应，请检查网络后刷新页面。")
        return

    st.subheader("📈 主要指数")
    idx_data = st.session_state.get('index_data')
    if idx_data is not None and not idx_data.empty:
        cols = st.columns(len(idx_data))
        for i, (_, row) in enumerate(idx_data.iterrows()):
            pct = row.get('pct_change', 0)
            sign = '+' if pct > 0 else ''
            color = '#ef4444' if pct > 0 else '#10b981' if pct < 0 else '#94a3b8'
            with cols[i]:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">{row['name']}</div>
                    <div class="metric-value" style="font-size:1.1rem">{row['price']:.2f}</div>
                    <div style="color:{color};font-size:0.85rem;font-weight:700">{sign}{pct:.2f}%</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("指数数据加载中...")

    st.divider()

    # 市场概况
    st.subheader("📋 市场总览")
    overview = st.session_state.get('overview', {})
    if overview:
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.markdown(f"""<div class="metric-card"><div class="metric-value" style="color:#ef4444">{overview.get('up',0)}</div><div class="metric-label">📈 上涨家数</div></div>""", unsafe_allow_html=True)
        c2.markdown(f"""<div class="metric-card"><div class="metric-value" style="color:#10b981">{overview.get('down',0)}</div><div class="metric-label">📉 下跌家数</div></div>""", unsafe_allow_html=True)
        c3.markdown(f"""<div class="metric-card"><div class="metric-value" style="color:#f97316">{overview.get('limit_up',0)}</div><div class="metric-label">🔥 涨停</div></div>""", unsafe_allow_html=True)
        c4.markdown(f"""<div class="metric-card"><div class="metric-value" style="color:#64748b">{overview.get('limit_down',0)}</div><div class="metric-label">❄️ 跌停</div></div>""", unsafe_allow_html=True)
        c5.markdown(f"""<div class="metric-card"><div class="metric-value" style="color:#fbbf24">{overview.get('total_amount',0):.0f}<span style="font-size:0.7rem">亿</span></div><div class="metric-label">💵 成交额</div></div>""", unsafe_allow_html=True)
        c6.markdown(f"""<div class="metric-card"><div class="metric-value">{overview.get('avg_pct',0):.2f}%</div><div class="metric-label">📊 平均涨跌</div></div>""", unsafe_allow_html=True)

    # 涨幅榜 + 跌幅榜
    df = st.session_state.get('market_data')
    if df is not None and not df.empty:
        st.divider()
        c_left, c_right = st.columns(2)

        with c_left:
            st.markdown("**🔥 涨幅榜 Top15**")
            top = df.nlargest(15, 'pct_change')
            display_cols = [c for c in ['code', 'name', 'price', 'pct_change', 'turnover', 'amount'] if c in df.columns]
            st.dataframe(top[display_cols], use_container_width=True, hide_index=True,
                         column_config={
                             'code': '代码', 'name': '名称',
                             'price': st.column_config.NumberColumn('价格', format='%.2f'),
                             'pct_change': st.column_config.NumberColumn('涨跌%', format='%.2f'),
                             'turnover': st.column_config.NumberColumn('换手%', format='%.2f'),
                             'amount': st.column_config.NumberColumn('成交额', format='%.0f'),
                         })

        with c_right:
            st.markdown("**❄️ 跌幅榜 Top15**")
            bottom = df.nsmallest(15, 'pct_change')
            st.dataframe(bottom[display_cols], use_container_width=True, hide_index=True,
                         column_config={
                             'code': '代码', 'name': '名称',
                             'price': st.column_config.NumberColumn('价格', format='%.2f'),
                             'pct_change': st.column_config.NumberColumn('涨跌%', format='%.2f'),
                             'turnover': st.column_config.NumberColumn('换手%', format='%.2f'),
                             'amount': st.column_config.NumberColumn('成交额', format='%.0f'),
                         })

        # 涨跌分布
        st.divider()
        st.markdown("**📊 涨跌分布**")
        bins = [-100, -9.9, -5, -3, -1, 0, 1, 3, 5, 9.9, 100]
        labels = ['跌停', '-5~-10%', '-3~-5%', '-1~-3%', '0~-1%', '0~+1%', '+1~3%', '+3~5%', '+5~10%', '涨停']
        df['range'] = pd.cut(df['pct_change'], bins=bins, labels=labels)
        dist = df['range'].value_counts().reindex(labels, fill_value=0)
        chart_data = pd.DataFrame({'涨跌区间': labels, '股票数量': dist.values})
        st.bar_chart(chart_data.set_index('涨跌区间'), use_container_width=True)

    else:
        st.warning("市场数据不可用，请检查网络或稍后刷新")
        if st.button("🔄 重新加载数据"):
            st.cache_data.clear()
            st.rerun()

    # 数据源信息
    st.caption(f"数据更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
               f"股票总数: {len(df) if df is not None else 0} | "
               "缓存10分钟自动刷新 | 点击右上角⋮→Rerun强制刷新")
