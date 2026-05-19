"""
Notification utility — placeholder for push alerts.
Can be extended to support Pushover / WeChat / DingTalk.
"""

from config import SystemConfig


class Notifier:
    """
    Sends alerts for circuit breaker events and other critical signals.
    Currently logs to console. Extend to support:
    - Pushover (pushover.net)
    - WeChat Work Bot (企业微信)
    - DingTalk Bot (钉钉)
    - Email / SMS
    """

    def __init__(self, channel: str = None):
        self.channel = channel or SystemConfig.NOTIFICATION_CHANNEL
        self.enabled = SystemConfig.NOTIFICATION_ENABLED

    def send_alert(self, title: str, message: str, level: str = "INFO"):
        """Send a push notification."""
        if not self.enabled:
            return

        full_msg = f"[{level}] {title}: {message}"

        if self.channel == "console":
            print(f"[NOTIFY] {full_msg}")

        elif self.channel == "pushover":
            # TODO: requests.post("https://api.pushover.net/1/messages.json", {...})
            print(f"[NOTIFY] Pushover: {full_msg}")

        elif self.channel == "wechat":
            # TODO: 企业微信机器人 webhook
            print(f"[NOTIFY] WeChat: {full_msg}")

        elif self.channel == "dingtalk":
            # TODO: 钉钉机器人 webhook
            print(f"[NOTIFY] DingTalk: {full_msg}")

        else:
            print(f"[NOTIFY] {full_msg}")

    def alert_circuit_breaker(self, declining_count: int):
        """Highest-priority alert for extreme market conditions."""
        self.send_alert(
            title="熔断警报",
            message=f"开盘下跌家数 {declining_count} > 4000，触发全仓清仓！",
            level="CRITICAL",
        )

    def alert_consecutive_loss(self, days: int):
        """Alert for consecutive loss days."""
        self.send_alert(
            title="连续亏损",
            message=f"已连续亏损 {days} 天，仓位上限已调整。",
            level="WARNING",
        )