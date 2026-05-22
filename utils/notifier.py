"""
推送通知模块。
支持企业微信、钉钉 Webhook 及 Telegram Bot。
使用后台线程异步发送，避免阻塞交易主循环，并内置频率限制（限流）。
"""

import json
import threading
from datetime import datetime
from typing import Dict, Optional

import requests

from config import Config
from utils.logger import get_logger

logger = get_logger("utils.notifier")


class Notifier:
    """消息通知服务。单例或可复用实例。"""

    def __init__(self):
        # topic_key -> last_sent_time
        self._last_sent: Dict[str, datetime] = {}
        self._rate_limit_secs = Config.NOTIFY.RATE_LIMIT_MINUTES * 60

    # ------------------------------------------------------------------
    # 核心发送逻辑
    # ------------------------------------------------------------------
    def send_alert(self, title: str, message: str, level: str = "INFO"):
        """
        发送通用通知。
        异步执行以避免阻塞引擎。
        """
        topic = f"{level}:{title}"
        
        # 频率限制检测（相同主题）
        now = datetime.now()
        last = self._last_sent.get(topic)
        if last and (now - last).total_seconds() < self._rate_limit_secs:
            logger.debug(f"[通知限流] 抑制发送: {topic}")
            return

        self._last_sent[topic] = now

        # 构建格式化文本
        icon = "🟢" if level == "INFO" else "🟡" if level == "WARNING" else "🔴"
        text = f"{icon} **{title}**\n\n> {message}\n\n*时间: {now.strftime('%H:%M:%S')}*"

        # 提交到后台线程发送
        t = threading.Thread(
            target=self._dispatch_all, 
            args=(title, text),
            daemon=True
        )
        t.start()

    def _dispatch_all(self, title: str, text: str):
        """分发给所有配置的渠道。"""
        if Config.NOTIFY.WECHAT_WEBHOOK:
            self._send_wechat(text)
        if Config.NOTIFY.DINGTALK_WEBHOOK:
            self._send_dingtalk(title, text)
        if Config.NOTIFY.TELEGRAM_BOT_TOKEN and Config.NOTIFY.TELEGRAM_CHAT_ID:
            self._send_telegram(text)

        # 兜底日志
        if not any([
            Config.NOTIFY.WECHAT_WEBHOOK, 
            Config.NOTIFY.DINGTALK_WEBHOOK,
            Config.NOTIFY.TELEGRAM_BOT_TOKEN
        ]):
            logger.debug(f"[无配置通知通道] 模拟推送: {title}")

    # ------------------------------------------------------------------
    # 各渠道实现
    # ------------------------------------------------------------------
    def _send_wechat(self, text: str):
        """企业微信机器人 Webhook (支持 Markdown)"""
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": text}
        }
        self._http_post("WeChat", Config.NOTIFY.WECHAT_WEBHOOK, payload)

    def _send_dingtalk(self, title: str, text: str):
        """钉钉机器人 Webhook (支持 Markdown)"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text
            }
        }
        self._http_post("DingTalk", Config.NOTIFY.DINGTALK_WEBHOOK, payload)

    def _send_telegram(self, text: str):
        """Telegram Bot"""
        url = f"https://api.telegram.org/bot{Config.NOTIFY.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": Config.NOTIFY.TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "MarkdownV2"
        }
        # 简单转义处理（TG MarkdownV2 要求严格）
        for char in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
            if char in ['*', '`', '[']: continue # 保留基本样式
            payload["text"] = payload["text"].replace(char, f"\\{char}")
            
        self._http_post("Telegram", url, payload)

    def _http_post(self, channel: str, url: str, payload: dict):
        try:
            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code != 200:
                logger.error(f"[{channel}] 发送失败 HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"[{channel}] 请求异常: {e}")

    # ------------------------------------------------------------------
    # 快捷业务通知方法
    # ------------------------------------------------------------------
    def alert_circuit_breaker(self, declining_count: int):
        self.send_alert(
            "开盘熔断",
            f"市场极端恶劣！下跌家数达 **{declining_count}**，\n"
            f"已触发系统自动保护机制，执行**一键全仓清仓**。",
            level="CRITICAL"
        )

    def alert_consecutive_loss(self, days: int):
        self.send_alert(
            "风控限仓",
            f"系统已连续亏损 **{days}** 个交易日。\n"
            f"根据账户风控规则，已触发强制清仓并暂停买入。",
            level="CRITICAL"
        )