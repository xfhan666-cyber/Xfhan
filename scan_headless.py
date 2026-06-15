"""
无人值守早盘扫描脚本 - GitHub Actions自动运行，无需开电脑
每天9:25自动运行 → 7策略扫描 → 企业微信推送到手机
"""
import os
import sys
import json
import time
from datetime import datetime

# Windows终端UTF-8编码修复（解决emoji输出报错问题）
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# 加载.env文件（本地使用）
try:
    with open(os.path.join(os.path.dirname(__file__), '.env'), 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())
except Exception:
    pass

# 绕过代理
for v in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    os.environ.pop(v, None)
os.environ['no_proxy'] = '*'
import requests
_orig = requests.Session.__init__
def _patched(self, *a, **kw):
    _orig(self, *a, **kw)
    self.trust_env = False
requests.Session.__init__ = _patched


def get_market_data():
    """获取全市场数据 - 多源尝试"""
    from data.fetcher import fetcher
    df = fetcher.get_realtime_all_stocks()
    if df is not None and not df.empty:
        return df

    # 最后的fallback: 直接用requests调用新浪API
    print("主数据源失败，尝试直连新浪...")
    import pandas as pd
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot()
        if df is not None and not df.empty:
            df = df.rename(columns={'代码': 'code', '名称': 'name', '最新价': 'price',
                                     '涨跌幅': 'pct_change', '成交量': 'volume', '成交额': 'amount',
                                     '最高': 'high', '最低': 'low', '今开': 'open', '昨收': 'pre_close'})
            df = df[df['price'] > 0].copy()
            df['is_st'] = df['name'].str.contains('ST|\\*ST', na=False)
            for col in ['pe_ratio', 'pb_ratio', 'market_cap', 'turnover', 'amplitude', 'volume_ratio']:
                if col not in df.columns:
                    df[col] = 0 if col != 'volume_ratio' else 1.0
            return df
    except Exception as e:
        print(f"新浪直连也失败: {e}")
    return None


def run_scan(market_data):
    """运行3大核心策略（超跌反弹+趋势动量+PB-ROE价值）"""
    from strategies.pb_roe import PBROEStrategy
    from strategies.trend_momentum import TrendMomentumStrategy
    from strategies.mean_reversion import MeanReversionStrategy
    from config import DEFAULT_STRATEGY_PARAMS

    STRATEGY_LABELS = {
        'mean_reversion': '超跌反弹',
        'trend_momentum': '趋势动量',
        'pb_roe': 'PB-ROE价值',
    }

    strategies = [
        ('mean_reversion', MeanReversionStrategy(DEFAULT_STRATEGY_PARAMS.get('mean_reversion'))),
        ('trend_momentum', TrendMomentumStrategy(DEFAULT_STRATEGY_PARAMS.get('trend_momentum'))),
        ('pb_roe', PBROEStrategy(DEFAULT_STRATEGY_PARAMS.get('pb_roe'))),
    ]

    all_signals = []
    for key, s in strategies:
        try:
            s.set_market_data(market_data)
            r = s.run()
            label = STRATEGY_LABELS.get(key, key)
            for sig in r.signals:
                sig.strategy = f'[{label}]{sig.strategy}'
            all_signals.extend(r.signals)
            print(f"  {label}: {len(r.signals)}个信号")
        except Exception as e:
            print(f"  {key}: 失败 - {e}")

    # 合并同股票多策略信号
    merged = {}
    for sig in all_signals:
        if sig.code not in merged:
            merged[sig.code] = sig
        else:
            merged[sig.code].confidence = min(95, merged[sig.code].confidence + 8)
            merged[sig.code].reason += ' | +' + sig.strategy
    return sorted(merged.values(), key=lambda x: x.confidence, reverse=True)


def send_wecom_webhook(webhook_url, content):
    """企业微信群机器人推送"""
    data = {"msgtype": "markdown", "markdown": {"content": content}}
    try:
        r = requests.post(webhook_url, json=data, timeout=15)
        return r.json().get('errcode') == 0
    except Exception as e:
        print(f"企业微信推送失败: {e}")
        return False


def send_pushplus(token, title, content):
    """PushPlus备用推送"""
    try:
        r = requests.get('http://www.pushplus.plus/send', params={
            'token': token, 'title': title, 'content': content, 'template': 'markdown'
        }, timeout=10)
        return r.json().get('code') == 200
    except Exception:
        return False


def send_serverchan(key, title, content):
    """Server酱备用推送"""
    try:
        r = requests.get(f'https://sctapi.ftqq.com/{key}.send', params={
            'title': title, 'desp': content
        }, timeout=10)
        return r.json().get('code') == 0
    except Exception:
        return False


def format_report(signals, market_info='', total_capital=100000, risk_level='moderate'):
    """格式化为Markdown推送内容，包含仓位分配"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [f"## 📈 A股早盘扫描 {now}", ""]

    if market_info:
        lines.append(f"> {market_info}")
        lines.append("")

    if not signals:
        lines.append("### ⚠️ 今日无符合条件信号")
        lines.append("当前市场环境不适合出击，空仓观望。")
        return '\n'.join(lines)

    # 仓位分配
    from portfolio.allocator import PortfolioAllocator
    allocator = PortfolioAllocator(total_capital=total_capital)
    plan = allocator.allocate(signals, risk_level=risk_level)

    if plan.allocations:
        lines.append(f"### 📋 今日买入清单 (总资金¥{total_capital:,})")
        lines.append("")
        for i, a in enumerate(plan.allocations[:5], 1):
            s = a.stock
            loss_amount = a.shares * (s.price - s.stop_loss)
            profit_amount = a.shares * (s.stop_profit - s.price)
            lines.append(f"**{i}. {s.name}({s.code})** {s.confidence:.0f}%")
            lines.append(f"> 买入: ¥{s.price} × **{a.shares}股({a.shares//100}手)** = ¥{a.amount:,.0f} ({a.weight}%)")
            lines.append(f"> 🛑止损: ¥{s.stop_loss} (亏¥{loss_amount:,.0f}) | 🎯止盈: ¥{s.stop_profit} (盈¥{profit_amount:,.0f})")
            lines.append(f"> {s.reason[:100]}")
            lines.append("")

        lines.append(f"---")
        lines.append(f"💰 总资金¥{plan.total_capital:,} | 使用¥{plan.used_capital:,.0f}({plan.used_capital/plan.total_capital*100:.0f}%) | 预留¥{plan.cash_reserved:,.0f}")
    else:
        # 无分配结果时回退到简单展示
        strong = [s for s in signals if s.confidence >= 75]
        medium = [s for s in signals if 55 <= s.confidence < 75]

        if strong:
            lines.append(f"### 🔥 强信号 ({len(strong)}个)")
            for i, s in enumerate(strong[:5], 1):
                lines.append(f"**{i}. {s.name}({s.code})** {s.confidence:.0f}%")
                lines.append(f"> 买入: {s.price} | 止损: {s.stop_loss} | 止盈: {s.stop_profit}")
                lines.append(f"> {s.reason[:100]}")
                lines.append("")

        if medium:
            lines.append(f"### 🟡 中等信号 ({len(medium)}个)")
            for s in medium[:5]:
                lines.append(f"- {s.name}({s.code}) {s.confidence:.0f}% | 买{s.price} 止{s.stop_loss}")
            lines.append("")

    lines.append("")
    lines.append(f"共扫描{len(signals)}个信号 | 🤖 自动推送")
    return '\n'.join(lines)


def main():
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now_str}] 早盘扫描开始...")
    print(f"   运行环境: {'GitHub Actions' if os.environ.get('GITHUB_ACTIONS') else '本地'}")
    print(f"   Python: {sys.version}")

    # 0. 输出配置状态（脱敏）
    print("0/4 检查推送配置...")
    has_wecom = bool(os.environ.get('WECOM_WEBHOOK', ''))
    has_pushplus = bool(os.environ.get('PUSHPLUS_TOKEN', ''))
    has_serverchan = bool(os.environ.get('SERVERCHAN_KEY', ''))
    print(f"   企业微信: {'✅已配置' if has_wecom else '❌未配置'}")
    print(f"   PushPlus: {'✅已配置' if has_pushplus else '❌未配置(推荐，免费200条/天)'}")
    print(f"   Server酱: {'✅已配置' if has_serverchan else '❌未配置(5条/天)'}")

    if not (has_wecom or has_pushplus or has_serverchan):
        print("")
        print("⚠️  警告: 所有推送通道均未配置！")
        print("   请访问 https://www.pushplus.plus 微信扫码获取Token")
        print("   然后添加到GitHub Secrets (PUSHPLUS_TOKEN) 或 .env 文件")
        print("")

    # 1. 获取数据
    print("1/4 获取市场数据...")
    t0 = time.time()
    market_data = get_market_data()
    if market_data is None or market_data.empty:
        print("❌ 数据获取失败！")
        # 尝试发错误通知（只有配置了的通道才发）
        pp_token = os.environ.get('PUSHPLUS_TOKEN', '')
        if pp_token:
            send_pushplus(pp_token, '⚠️ 量化扫描异常', f"时间: {now_str}\n数据获取失败，请检查网络或AKShare数据源。")
        sys.exit(1)

    elapsed = time.time()-t0
    print(f"   ✅ 获取{len(market_data)}只股票，耗时{elapsed:.0f}秒")

    # 市场概况
    up_count = len(market_data[market_data['pct_change'] > 0]) if 'pct_change' in market_data.columns else 0
    total = len(market_data)
    up_ratio = up_count / total * 100 if total > 0 else 0
    market_note = f"上涨{up_count}家({up_ratio:.0f}%)"
    if up_ratio > 60:
        market_note += " 🟢强势"
    elif up_ratio > 40:
        market_note += " 🟡震荡"
    elif up_ratio > 20:
        market_note += " 🟠弱势"
    else:
        market_note += " 🔴极端"

    # 2. 运行策略
    print("2/4 运行3大核心策略扫描...")
    signals = run_scan(market_data)
    print(f"   ✅ 共发现{len(signals)}个信号")

    if signals:
        strong_count = len([s for s in signals if s.confidence >= 75])
        medium_count = len([s for s in signals if 55 <= s.confidence < 75])
        print(f"   强信号🔥: {strong_count}个 | 中等🟡: {medium_count}个")

    # 3. 推送（改进：PushPlus优先作为主力通道，免费200条/天最实用）
    print("3/4 推送到手机...")
    # 默认10万资金、稳健模式（GitHub Actions环境变量可覆盖）
    capital = float(os.environ.get('TOTAL_CAPITAL', 100000))
    risk = os.environ.get('RISK_LEVEL', 'moderate')
    report = format_report(signals, market_note, total_capital=capital, risk_level=risk)

    push_results = []

    # 通道1: PushPlus（推荐主力，200条/天免费）
    pp_token = os.environ.get('PUSHPLUS_TOKEN', '')
    if pp_token:
        ok = send_pushplus(pp_token, 'A股早盘扫描', report)
        push_results.append(f"PushPlus: {'✅' if ok else '❌'}")
        if ok:
            print(f"   ✅ PushPlus 推送成功")
        else:
            print(f"   ❌ PushPlus 推送失败")
    else:
        push_results.append("PushPlus: ⚪未配置")

    # 通道2: 企业微信机器人
    webhook = os.environ.get('WECOM_WEBHOOK', '')
    if webhook:
        ok = send_wecom_webhook(webhook, report)
        push_results.append(f"企业微信: {'✅' if ok else '❌'}")
        if ok:
            print(f"   ✅ 企业微信 推送成功")
    else:
        push_results.append("企业微信: ⚪未配置")

    # 通道3: Server酱（备用，5条/天）
    # 兼容两种命名：SERVERCHAN_KEY(旧) 和 SERVERCHAN_KEY1(新)
    sc_key = os.environ.get('SERVERCHAN_KEY', '') or os.environ.get('SERVERCHAN_KEY1', '')
    if sc_key:
        ok = send_serverchan(sc_key, 'A股早盘扫描', report)
        push_results.append(f"Server酱: {'✅' if ok else '❌'}")
        if ok:
            print(f"   ✅ Server酱 推送成功")
    else:
        push_results.append("Server酱: ⚪未配置")

    # 4. 输出报告（用于日志）
    print("4/4 扫描报告:")
    print(report)
    print("")
    print(f"[{datetime.now()}] 推送结果: {' | '.join(push_results)}")

    any_success = any('✅' in r for r in push_results)
    if any_success:
        print(f"[{datetime.now()}] 🎉 扫描完成，已推送到手机！")
    else:
        print(f"[{datetime.now()}] ⚠️ 所有推送通道均失败或未配置！")
        print("")
        print("📱 快速配置PushPlus（推荐）:")
        print("   1. 打开 https://www.pushplus.plus 微信扫码")
        print("   2. 复制Token")
        print("   3. 在GitHub仓库 Settings→Secrets→Actions 添加 PUSHPLUS_TOKEN")
        print("   4. 同时在本地 .env 文件添加: PUSHPLUS_TOKEN=你的token")
        sys.exit(1)


if __name__ == '__main__':
    main()
