"""
消息推送模块 - PushPlus优先(200条/天) ← Server酱(5条/天) ← 企业微信(无限,最隐私)
隐私说明：
- 企业微信: 消息直连你的企业微信服务器→微信，不经任何第三方，最安全
- PushPlus: 消息经pushplus.plus转发，不存储内容，注册只需微信扫码
- Server酱: 消息经sct.ftqq.com转发，5条/天仅够测试
推荐: 用量大选企业微信(无限+隐私)，用量中等选PushPlus(200/天)
"""
import requests
from typing import List
from datetime import datetime
from strategies.base_strategy import TradeSignal
from config import WECOM_CORP_ID, WECOM_CORP_SECRET, WECOM_AGENT_ID, PUSHPLUS_TOKEN, SERVERCHAN_KEY


class Notifier:
    def __init__(self):
        self.wecom_token = None
        self.wecom_token_time = None
        self._sent_count = 0

    def _send_pushplus(self, title: str, content: str) -> bool:
        """PushPlus推送 (200条/天, 主力通道)"""
        if not PUSHPLUS_TOKEN:
            return False
        try:
            resp = requests.get('http://www.pushplus.plus/send', params={
                'token': PUSHPLUS_TOKEN, 'title': title,
                'content': content, 'template': 'markdown'
            }, timeout=10).json()
            return resp.get('code') == 200
        except Exception:
            return False

    def _send_serverchan(self, title: str, content: str) -> bool:
        """Server酱 (5条/天, 备用)"""
        if not SERVERCHAN_KEY:
            return False
        try:
            resp = requests.get(f'https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send', params={
                'title': title, 'desp': content
            }, timeout=10).json()
            return resp.get('code') == 0
        except Exception:
            return False

    def _send_wecom(self, title: str, content: str) -> bool:
        """企业微信 (无限条, 最隐私 - 直连你的服务器)"""
        if not all([WECOM_CORP_ID, WECOM_CORP_SECRET, WECOM_AGENT_ID]):
            return False
        if not self.wecom_token or (datetime.now() - self.wecom_token_time).seconds > 7000:
            try:
                resp = requests.get(
                    f'https://qyapi.weixin.qq.com/cgi-bin/gettoken',
                    params={'corpid': WECOM_CORP_ID, 'corpsecret': WECOM_CORP_SECRET}, timeout=10
                ).json()
                self.wecom_token = resp.get('access_token')
                self.wecom_token_time = datetime.now()
            except Exception:
                return False
        try:
            resp = requests.post(
                f'https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={self.wecom_token}',
                json={"touser": "@all", "msgtype": "markdown", "agentid": WECOM_AGENT_ID,
                      "markdown": {"content": f"## {title}\n{content}"}}, timeout=10
            ).json()
            return resp.get('errcode') == 0
        except Exception:
            return False

    def send(self, title: str, content: str) -> dict:
        """智能发送：企业微信 → PushPlus → Server酱"""
        result = {'wecom': False, 'pushplus': False, 'serverchan': False}
        if self._send_wecom(title, content):
            result['wecom'] = True
        elif self._send_pushplus(title, content):
            result['pushplus'] = True
        elif self._send_serverchan(title, content):
            result['serverchan'] = True
        if any(result.values()):
            self._sent_count += 1
        return result

    def send_signal(self, signal: TradeSignal) -> dict:
        """发送单条交易信号"""
        act = signal.action
        emoji = '🔥' if signal.confidence >= 80 else ('🔴' if act == 'BUY' else '🟢')
        title = f"{emoji} [{act}] {signal.name}({signal.code}) 置信度{signal.confidence:.0f}%"
        content = f"""
> 策略: **{signal.strategy}**
> 建议价: **{signal.price}** | 止损: {signal.stop_loss} | 止盈: {signal.stop_profit}

**理由:** {signal.reason}

{signal.timestamp}
"""
        return self.send(title, content)

    def send_price_alert(self, code: str, name: str, target_price: float, current_price: float, direction: str) -> dict:
        """价格到价提醒"""
        d = '📈 上涨到' if direction == 'up' else '📉 下跌到'
        title = f"⏰ [到价提醒] {name}({code})"
        content = f"""
> {d} **{target_price}** 元
> 当前价: {current_price} | 差额: {abs(current_price - target_price):.2f}

请确认是否执行操作。
"""
        return self.send(title, content)

    def send_batch(self, signals: List[TradeSignal], max_send: int = 5) -> dict:
        top = sorted(signals, key=lambda s: s.confidence, reverse=True)[:max_send]
        ok = 0
        for s in top:
            if any(self.send_signal(s).values()):
                ok += 1
        return {'total': len(signals), 'sent': len(top), 'success': ok}

    def test(self) -> dict:
        r = {}
        r['企业微信'] = '✅' if WECOM_CORP_ID else '⚪未配置'
        r['PushPlus'] = '✅' if PUSHPLUS_TOKEN else '⚪未配置(推荐,200条/天)'
        r['Server酱'] = '✅已配置(5条/天)' if SERVERCHAN_KEY else '⚪未配置'
        return r


notifier = Notifier()
