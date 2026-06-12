"""
无人值守早盘扫描脚本 - GitHub Actions自动运行，无需开电脑
每天9:25自动运行 → 7策略扫描 → 企业微信推送到手机
"""
import os
import sys
import json
import time
from datetime import datetime

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
    """运行全部7个策略"""
    from strategies.multi_factor import MultiFactorStrategy
    from strategies.pb_roe import PBROEStrategy
    from strategies.trend_momentum import TrendMomentumStrategy
    from strategies.mean_reversion import MeanReversionStrategy
    from strategies.smallcap_growth import SmallCapGrowthStrategy
    from strategies.first_board import FirstBoardStrategy
    from strategies.limit_up import LimitUpStrategy
    from config import DEFAULT_STRATEGY_PARAMS

    strategies = [
        ('多因子', MultiFactorStrategy(DEFAULT_STRATEGY_PARAMS.get('multi_factor'))),
        ('PB-ROE', PBROEStrategy(DEFAULT_STRATEGY_PARAMS.get('pb_roe'))),
        ('趋势动量', TrendMomentumStrategy(DEFAULT_STRATEGY_PARAMS.get('trend_momentum'))),
        ('超跌反弹', MeanReversionStrategy(DEFAULT_STRATEGY_PARAMS.get('mean_reversion'))),
        ('小盘成长', SmallCapGrowthStrategy(DEFAULT_STRATEGY_PARAMS.get('smallcap_growth'))),
        ('涨停板', LimitUpStrategy(DEFAULT_STRATEGY_PARAMS.get('limit_up'))),
        ('首板打板', FirstBoardStrategy(DEFAULT_STRATEGY_PARAMS.get('first_board'))),
    ]

    all_signals = []
    for label, s in strategies:
        try:
            s.set_market_data(market_data)
            r = s.run()
            for sig in r.signals:
                sig.strategy = f'[{label}]{sig.strategy}'
            all_signals.extend(r.signals)
            print(f"  {label}: {len(r.signals)}个信号")
        except Exception as e:
            print(f"  {label}: 失败 - {e}")

    # 合并同股票多策略信号
    merged = {}
    for sig in all_signals:
        if sig.code not in merged:
            merged[sig.code] = sig
        else:
            merged[sig.code].confidence = min(98, merged[sig.code].confidence + 5)
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


def format_report(signals, market_info=''):
    """格式化为Markdown推送内容"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [f"## 📈 A股早盘扫描 {now}", ""]

    if market_info:
        lines.append(f"> {market_info}")
        lines.append("")

    if not signals:
        lines.append("### ⚠️ 今日无符合条件信号")
        lines.append("当前市场环境不适合出击，空仓观望。")
        return '\n'.join(lines)

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

    lines.append("---")
    lines.append(f"共扫描{len(signals)}个信号 | 数据来源: AKShare/Sina")
    return '\n'.join(lines)


def main():
    print(f"[{datetime.now()}] 早盘扫描开始...")

    # 1. 获取数据
    print("1/3 获取市场数据...")
    t0 = time.time()
    market_data = get_market_data()
    if market_data is None or market_data.empty:
        print("数据获取失败！")
        # 尝试发错误通知
        webhook = os.environ.get('WECOM_WEBHOOK', '')
        if webhook:
            send_wecom_webhook(webhook, f"## ⚠️ 量化扫描异常\n{datetime.now()}\n数据获取失败，请检查。")
        sys.exit(1)
    print(f"   获取{len(market_data)}只股票，耗时{time.time()-t0:.0f}秒")

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
    print("2/3 运行7策略扫描...")
    signals = run_scan(market_data)
    print(f"   共发现{len(signals)}个信号")

    # 3. 推送
    print("3/3 推送到手机...")
    report = format_report(signals, market_note)

    pushed = False
    # 主通道: 企业微信群机器人
    webhook = os.environ.get('WECOM_WEBHOOK', '')
    if webhook:
        pushed = send_wecom_webhook(webhook, report)
        print(f"   企业微信: {'成功' if pushed else '失败'}")

    # 备用: PushPlus
    if not pushed:
        pp_token = os.environ.get('PUSHPLUS_TOKEN', '')
        if pp_token:
            pushed = send_pushplus(pp_token, 'A股早盘扫描', report)
            print(f"   PushPlus: {'成功' if pushed else '失败'}")

    # 备用: Server酱
    if not pushed:
        sc_key = os.environ.get('SERVERCHAN_KEY', '')
        if sc_key:
            pushed = send_serverchan(sc_key, 'A股早盘扫描', report)
            print(f"   Server酱: {'成功' if pushed else '失败'}")

    if not pushed:
        print("所有推送通道均失败！请检查配置。")
        print(report)  # 至少打印出来
        sys.exit(1)

    print(f"[{datetime.now()}] 扫描完成，已推送到手机！")


if __name__ == '__main__':
    main()
