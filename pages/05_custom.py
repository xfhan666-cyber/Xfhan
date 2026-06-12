"""
我的策略 - YAML策略编辑器 + 加载运行
"""
import streamlit as st
from custom.strategy_loader import loader

EXAMPLE_YAML = """strategy_name: "高股息防守策略"
description: "筛选高股息率、低估值、低波动的防守型股票"

conditions:
  must_include:
    - "dividend_yield > 3"
    - "daily_volume > 20000000"
    - "pe_ratio < 20"
    - "pe_ratio > 0"
    - "is_st == false"

  ranking_factors:
    - field: "dividend_yield"
      weight: 40
      order: "desc"
    - field: "volatility_60d"
      weight: 30
      order: "asc"
    - field: "roe"
      weight: 20
      order: "desc"
    - field: "market_cap"
      weight: 10
      order: "desc"

  position:
    max_stocks: 10
    single_weight: "equal"
    max_single_pct: 15

  rebalance:
    frequency: "monthly"
    day_of_month: 1

  risk_control:
    stop_loss_pct: 8
    stop_profit_pct: 25
    max_drawdown_portfolio: 15
"""


def show():
    st.subheader("⚙️ 我的策略")

    tab1, tab2, tab3 = st.tabs(["📝 策略编辑器", "📂 已保存策略", "▶️ 运行策略"])

    with tab1:
        st.markdown("""
        ### 支持的筛选字段
        | 字段名 | 说明 | 示例 |
        |--------|------|------|
        | `pe_ratio` | 市盈率 | `pe_ratio < 20` |
        | `pb_ratio` | 市净率 | `pb_ratio < 3` |
        | `roe` | ROE(%) | `roe > 15` |
        | `dividend_yield` | 股息率(%) | `dividend_yield > 3` |
        | `market_cap` | 总市值(元) | `market_cap < 20000000000` |
        | `turnover` | 换手率(%) | `turnover > 2` |
        | `pct_change` | 涨跌幅(%) | `pct_change > -5` |
        | `pct_ytd` | 年初至今涨跌 | `pct_ytd > -10` |
        | `volatility_60d` | 60日涨跌(波动) | `volatility_60d < 15` |
        | `daily_volume` | 日成交额(元) | `daily_volume > 20000000` |
        | `is_st` | 是否ST | `is_st == false` |
        """)

        col1, col2 = st.columns([3, 1])
        with col1:
            yaml_input = st.text_area("YAML配置", value=EXAMPLE_YAML, height=400, key="yaml_editor")
        with col2:
            filename = st.text_input("文件名", "my_strategy.yaml")
            if st.button("💾 保存", use_container_width=True):
                if loader.save_strategy(filename, yaml_input):
                    st.toast(f"✅ {filename} 已保存!")
                else:
                    st.error("保存失败")
            if st.button("📋 加载示例", use_container_width=True):
                st.session_state.yaml_editor = EXAMPLE_YAML
                st.rerun()

    with tab2:
        strategies = loader.list_strategies()
        if not strategies:
            st.info("暂无已保存的策略，在左侧「策略编辑器」中创建")
        else:
            for s in strategies:
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.markdown(f"**{s['name']}**")
                c1.caption(f"{s['description']} | {s['filename']}")
                if c2.button("▶️ 运行", key=f"run_{s['filename']}"):
                    st.session_state.run_strategy_file = s['filename']
                if c3.button("🗑️ 删除", key=f"del_{s['filename']}"):
                    loader.delete_strategy(s['filename'])
                    st.rerun()

    with tab3:
        file_to_run = st.session_state.get('run_strategy_file', '')
        saved = loader.list_strategies()
        file_names = [s['filename'] for s in saved]
        if not file_names:
            st.info("请先在策略编辑器中创建并保存策略")
            return

        selected_file = st.selectbox("选择策略", file_names, index=file_names.index(file_to_run) if file_to_run in file_names else 0)

        if st.button("🚀 执行策略", type="primary"):
            market_data = st.session_state.get('market_data')
            if market_data is None or market_data.empty:
                st.error("市场数据未就绪")
                return

            try:
                strategy = loader.load_strategy(selected_file)
                strategy.set_market_data(market_data)
                with st.spinner(f"运行 {strategy.name}..."):
                    result = strategy.run()

                st.success(f"策略: {strategy.name}")
                if not result.selected_stocks.empty:
                    st.dataframe(result.selected_stocks.head(20), use_container_width=True, hide_index=True)
                if result.signals:
                    st.subheader("交易信号")
                    for s in result.signals[:10]:
                        st.markdown(f"""
                        <div class="signal-card signal-card-buy">
                            <strong>{s.name} ({s.code})</strong> 置信度: {s.confidence:.0f}%
                            <br>建议价: {s.price} | 止损: {s.stop_loss} | 止盈: {s.stop_profit}
                            <br>📝 {s.reason}
                        </div>
                        """, unsafe_allow_html=True)
                st.text(result.summary)
            except Exception as e:
                st.error(f"运行失败: {e}")
                st.info("请检查YAML格式是否正确，字段名是否在支持列表中")
