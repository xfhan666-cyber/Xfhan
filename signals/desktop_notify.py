"""
Windows桌面通知 - 完全本地，零隐私风险，无需注册，不限条数
使用Python内置ctypes调用Windows API，不需要安装任何第三方包
"""
import ctypes
import subprocess
import sys
import os


def show_windows_toast(title: str, message: str) -> bool:
    """
    Windows 10/11 原生通知（右下角弹出）
    使用内置PowerShell，无需安装任何东西
    """
    # 清理消息中的特殊字符
    safe_title = title.replace('"', "'").replace('`', "'")
    safe_msg = message.replace('"', "'").replace('`', "'")

    ps_script = f'''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$txt = $tpl.GetElementsByTagName("text")
$txt.Item(0).AppendChild($tpl.CreateTextNode("{safe_title}")) | Out-Null
$txt.Item(1).AppendChild($tpl.CreateTextNode("{safe_msg}")) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($tpl)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("A股量化系统").Show($toast)
'''
    try:
        # 使用Windows PowerShell（不是PowerShell Core）
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script],
            capture_output=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        return result.returncode == 0
    except Exception:
        return False


def show_popup(title: str, message: str) -> bool:
    """
    备用方案：Windows MessageBox弹窗
    100%可用，任何Windows版本都支持
    """
    try:
        ctypes.windll.user32.MessageBoxW(
            0, message, title, 0x40 | 0x1  # 0x40=信息图标, 0x1=确定按钮
        )
        return True
    except Exception:
        return False


def notify(title: str, message: str) -> bool:
    """
    发送桌面通知：优先原生Toast → 回退MessageBox
    """
    if show_windows_toast(title, message):
        return True
    return show_popup(title, message)


def notify_signal(stock_name: str, stock_code: str, action: str,
                  price: float, confidence: float, reason: str) -> bool:
    """发送交易信号桌面通知"""
    emoji = '🔴买入' if action == 'BUY' else '🟢卖出'
    title = f'{emoji} | {stock_name}({stock_code})'
    msg = f'置信度: {confidence:.0f}%\n'
    msg += f'建议价: {price}元\n'
    msg += f'理由: {reason[:80]}'
    return notify(title, msg)


def notify_price_alert(stock_name: str, stock_code: str,
                       target_price: float, current_price: float) -> bool:
    """价格到价提醒"""
    title = f'⏰ 到价提醒 | {stock_name}({stock_code})'
    msg = f'目标价: {target_price}元\n'
    msg += f'当前价: {current_price}元\n'
    msg += '请确认是否操作'
    return notify(title, msg)


def test():
    """测试桌面通知"""
    return notify('A股量化系统', '桌面通知测试成功！\n系统运行正常，收到信号时将自动弹出提醒。')
