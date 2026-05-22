"""
实时日志捕获与分发模块。
捕获 `logger.py` 的输出，通过 WebSocket 广播给前端页面。
"""

import logging
import asyncio
from typing import List, Set
from datetime import datetime

class WebSocketLogHandler(logging.Handler):
    """
    自定义 LogHandler，拦截日志并缓存至内存。
    当有 WebSocket 客户端连接时进行推送。
    """
    def __init__(self, capacity: int = 200):
        super().__init__()
        self.capacity = capacity
        # 缓存最近的 N 条日志，给新连入的客户端看历史记录
        self.history: List[dict] = []
        # 当前连接的客户端队列，存放 asyncio.Queue
        self.queues: Set[asyncio.Queue] = set()

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            log_item = {
                "timestamp": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": record.levelname,
                "name": record.name,
                "message": msg
            }

            # 维护历史
            self.history.append(log_item)
            if len(self.history) > self.capacity:
                self.history.pop(0)

            # 向所有订阅的队列推送
            for q in list(self.queues):
                # non-blocking put
                try:
                    q.put_nowait(log_item)
                except asyncio.QueueFull:
                    pass
        except Exception:
            self.handleError(record)

    def subscribe(self) -> asyncio.Queue:
        """注册一个新客户端队列"""
        q = asyncio.Queue(maxsize=100)
        self.queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        """取消注册"""
        if q in self.queues:
            self.queues.remove(q)

# 全局单例
ws_log_handler = WebSocketLogHandler()
ws_log_handler.setLevel(logging.INFO)
ws_log_handler.setFormatter(logging.Formatter("%(message)s"))

def attach_to_logger():
    """将 handler 附加到 qmt_ths 根 logger"""
    import logging
    logger = logging.getLogger("qmt_ths")
    if ws_log_handler not in logger.handlers:
        logger.addHandler(ws_log_handler)
