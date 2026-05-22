"""
Engine Manager — 管理盘中引擎与盘后选股器的执行与生命周期。
允许通过 API 触发异步任务或后台线程运行。
"""

import threading
import traceback
from typing import Dict, Any, Optional
import os

from data.market_data import MarketData
from data.portfolio import Portfolio
from core.intraday_engine import IntradayEngine
from run_screening import run_screening
from config import Config
from utils.logger import get_logger

logger = get_logger("core.manager")


class EngineManager:
    """管理交易引擎的单例"""
    def __init__(self):
        self.md = MarketData()
        self.portfolio = Portfolio()
        self.engine = IntradayEngine(self.md, self.portfolio)
        
        self._thread: Optional[threading.Thread] = None
        self._screening_thread: Optional[threading.Thread] = None

    def load_watchlist(self):
        """从文件加载选股池"""
        filepath = os.path.join(Config.SYSTEM.DATA_DIR, Config.SYSTEM.WATCHLIST_FILE)
        if not os.path.exists(filepath):
            logger.warning(f"监控池文件不存在: {filepath}")
            self.engine.load_watchlist([])
            return
            
        with open(filepath, "r", encoding="utf-8") as f:
            codes = [line.strip() for line in f if line.strip()]
        self.engine.load_watchlist(codes)

    def start_intraday(self):
        """启动盘中引擎（后台线程）"""
        if self.is_intraday_running():
            logger.warning("盘中引擎已经在运行中")
            return

        self.load_watchlist()

        self._thread = threading.Thread(target=self._run_engine_safely, daemon=True)
        self._thread.start()

    def stop_intraday(self):
        """停止盘中引擎"""
        if not self.is_intraday_running():
            return
        self.engine.stop()
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _run_engine_safely(self):
        try:
            self.engine.start()
        except Exception as e:
            logger.error(f"引擎线程异常退出: {e}\n{traceback.format_exc()}")
        finally:
            self.engine.is_running = False

    def is_intraday_running(self) -> bool:
        return self.engine.is_running and self._thread is not None and self._thread.is_alive()

    def start_nightly_screening(self):
        """启动盘后选股器（后台线程）"""
        if self.is_screening_running():
            logger.warning("盘后选股器正在运行中")
            return
            
        self._screening_thread = threading.Thread(target=self._run_screening_safely, daemon=True)
        self._screening_thread.start()
        
    def _run_screening_safely(self):
        try:
            logger.info("开始执行后台盘后选股任务...")
            run_screening()
            # 选股完成后自动重新加载到盘中引擎
            self.load_watchlist()
            logger.info("后台盘后选股任务完成")
        except Exception as e:
            logger.error(f"选股线程异常: {e}\n{traceback.format_exc()}")

    def is_screening_running(self) -> bool:
        return self._screening_thread is not None and self._screening_thread.is_alive()

    def get_status(self) -> Dict[str, Any]:
        """获取引擎整体状态"""
        return {
            "intraday_running": self.is_intraday_running(),
            "screening_running": self.is_screening_running(),
            "watchlist_count": len(self.engine.watchlist)
        }

# 全局单例
manager = EngineManager()
