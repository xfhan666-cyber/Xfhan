"""
交易信号 - 综合所有策略信号 + 手机推送
"""
import streamlit as st
from signals.generator import generator
from signals.notifier import notifier


def show():
    if st.session_state.get('market_data') is None:
        st.info("⏳ 数据加载中，请等待仪表盘数据就绪后再扫描信号...")
        return
    st.subheader("📶 交易信号中心")

    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("🔍 扫描全市场生成信号", type="primary", use_container_width=True):
            market_data = st.session_state.get('market_data')
            if market_data is None or market_data.empty:
                st.error("市场数据未就绪，请等待仪表盘数据加载完成")
            else:
                with st.spinner("正在运行7个策略扫描全市场..."):
                    signals = generator.run_all_strategies(market_data)
                    st.success(f"扫描完成！共生成 {len(signals)} 条交易信号")
                    st.rerun()

    with col2:
        if st.button("🧪 测试推送连接", use_container_width=True):
            result = notifier.test_connection()
            for k, v in result.items():
                st.caption(f"{k}: {v}")

    # 显示信号
    buy_signals = generator.get_buy_signals()
    sell_signals = generator.get_sell_signals()

    if not buy_signals and not sell_signals:
        st.info("""
        💡 **暂无交易信号**

        点击上方「扫描全市场生成信号」按钮，系统将同时运行7个策略：
        - 🎯 多因子综合打分
        - 💎 PB-ROE价值精选
        - 🚀 趋势动量+资金流
        - 🎢 超跌反弹
        - 🌱 小盘成长轮动
        - 🔥 涨停板跟踪
        - ⚡ 首板打板策略

        **多策略共识的信号会自动提升置信度！**
        """)
        return

    # 买入信号
    if buy_signals:
        st.subheader(f"🔴 买入信号 ({len(buy_signals)}条)")

        min_conf = st.slider("最低置信度过滤", 0, 100, 50, help="只显示置信度高于此值的信号")
        filtered = [s for s in buy_signals if s.confidence >= min_conf]
        filtered.sort(key=lambda s: s.confidence, reverse=True)

        for s in filtered[:20]:
            conf_color = '#ef4444' if s.confidence >= 80 else '#f59e0b' if s.confidence >= 60 else '#94a3b8'
            st.markdown(f"""
            <div class="signal-card signal-card-buy">
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <div>
                        <span style="font-size:1.1rem;font-weight:700">{s.name}</span>
                        <span style="color:#94a3b8;margin-left:8px;font-size:0.85rem">{s.code}</span>
                    </div>
                    <span style="background:rgba(239,68,68,.15);color:#ef4444;padding:4px 12px;border-radius:12px;font-weight:700;font-size:0.85rem">
                        {s.confidence:.0f}%
                    </span>
                </div>
                <div style="margin-top:6px;font-size:0.85rem;color:#cbd5e1">
                    策略: <strong>{s.strategy}</strong> |
                    建议买入价: <strong style="color:#fbbf24">{s.price}</strong> |
                    止损: <span style="color:#ef4444">{s.stop_loss}</span> |
                    止盈: <span style="color:#10b981">{s.stop_profit}</span>
                </div>
                <div style="margin-top:4px;font-size:0.8rem;color:#94a3b8">📝 {s.reason}</div>
                <div style="margin-top:4px;font-size:0.7rem;color:#64748b">{s.timestamp}</div>
            </div>
            """, unsafe_allow_html=True)

            # 桌面通知按钮（免费+隐私+不限条数）
            if st.button(f"🔔 弹窗提醒", key=f"popup_{s.code}_{id(s)}"):
                from signals.desktop_notify import notify_signal
                notify_signal(s.name, s.code, s.action, s.price, s.confidence, s.reason)
                st.toast("✅ 已弹出桌面通知!")
            # 微信推送按钮（需配置，作为可选）
            if st.button(f"📱 推送到微信", key=f"wx_{s.code}_{id(s)}"):
                result = notifier.send_signal(s)
                if any(result.values()):
                    st.toast("✅ 已推送到微信!")
                else:
                    st.info("微信推送未配置。桌面通知无需配置，免费无限使用。")

    # 卖出信号
    if sell_signals:
        st.subheader(f"🟢 卖出/止盈信号 ({len(sell_signals)}条)")
        for s in sell_signals[:10]:
            st.markdown(f"""
            <div class="signal-card signal-card-sell">
                <strong>{s.name} ({s.code})</strong> |
                建议卖出价: {s.price} |
                策略: {s.strategy}
                <br><span style="color:#94a3b8;font-size:0.8rem">📝 {s.reason}</span>
            </div>
            """, unsafe_allow_html=True)

    # 通知方式说明
    with st.expander("📱 通知方式对比（点击展开）"):
        st.markdown("""
        ### 🔔 桌面弹窗通知（推荐，已内置）
        - **费用**: 完全免费
        - **条数**: 无限
        - **隐私**: 100%本地，数据不出电脑
        - **注册**: 不需要！什么都不用填
        - **效果**: Windows右下角弹出通知 + 可选弹窗
        - **缺点**: 只在电脑前能看到

        ### 📱 微信推送（可选，需额外配置）
        - Server酱: 已配置(5条/天)，仅作备用
        - PushPlus: 需要注册但要身份证，不推荐
        - 企业微信: 无限条+最隐私，但注册略麻烦

        ### 实际使用建议
        日常用 **桌面弹窗**（免费无限隐私），偶尔需要手机收消息时用Server酱。
        大部分时候你开盘前坐在电脑前扫描一下，看到信号设好券商条件单就够了，
        不需要24小时手机推送。
        """)
