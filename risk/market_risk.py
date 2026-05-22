"""
市场级风控 — 开盘熔断检测。
在交易日开始的前 10 分钟监测极端市场条件。

变更记录：
  v1.1  - 修复 Bug #6：修正配置名（CIRCUIT_BREAKER_ADVANCING_BELOW 实为 declining 阈值）
        - 修复 Bug #6：非熔断时间窗口时，position_cap 自动重置为 1.0
        - 移除内联 lambda push_alert，改为依赖注入 Notifier
        - 使用 get_logger 替代 print
"""

from datetime import datetime
from typing import Optional

from config import Config
from data.market_data import MarketData
from utils.logger import get_logger

logger = get_logger("risk.market")


class MarketRiskController:
    """
    开盘熔断检测（09:30–09:40）：
    - 下跌家数 > 4000 → 全仓清仓
    - 下跌家数 > 3000 → 仓位上限 50%
    """

    def __init__(self, market_data: MarketData, notifier=None):
        self.md = market_data
        # 可选注入 Notifier；默认为 None（不推送）
        self.notifier = notifier
        self.position_cap: float = 1.0

    # ------------------------------------------------------------------
    # 熔断检测
    # ------------------------------------------------------------------
    def check_circuit_breaker(self) -> str:
        """
        检查开盘熔断条件。
        返回："full_liquidation" | "half_cap" | "normal"

        修复 Bug #6a：
          - 配置名 CIRCUIT_BREAKER_ADVANCING_BELOW 实际用于比较 declining 数量，
            已更新注释并修正逻辑（比较对象为 declining，不是 advancing）。
        修复 Bug #6b：
          - 非熔断时间窗口时，position_cap 重置为 1.0，
            避免前一个 tick 设置的值在后续 tick 持续生效。
        """
        now = datetime.now().time()
        cb_start = Config.TRADING_TIME.CIRCUIT_BREAKER_START
        cb_end = Config.TRADING_TIME.CIRCUIT_BREAKER_END

        if not (cb_start <= now <= cb_end):
            # 非熔断窗口：重置仓位上限（修复 Bug #6b）
            self.position_cap = 1.0
            return "normal"

        advancing, declining, flat = self.md.get_market_advancing_declining()
        logger.debug(
            f"[熔断检测] 涨={advancing} 跌={declining} 平={flat}"
        )

        # 注意：配置名 CIRCUIT_BREAKER_ADVANCING_BELOW 语义上是
        # "下跌家数超过此值触发最高级别"，与 advancing 无关。
        # 下跌 > 4000 → 全仓清仓
        full_liq_threshold = Config.MACRO.CIRCUIT_BREAKER_ADVANCING_BELOW
        half_cap_threshold = Config.MACRO.CIRCUIT_BREAKER_ADVANCING_WARNING

        if declining > full_liq_threshold:
            msg = (
                f"[最高级别] 开盘熔断警报！下跌家数 {declining} > "
                f"{full_liq_threshold}，触发全仓清仓！"
            )
            logger.critical(msg)
            if self.notifier:
                self.notifier.alert_circuit_breaker(declining)
            self.position_cap = 0.0
            return "full_liquidation"

        # 下跌 > 3000 → 半仓上限
        if declining > half_cap_threshold:
            logger.warning(
                f"[熔断警告] 下跌家数 {declining} > {half_cap_threshold}，"
                f"仓位上限调整为 50%"
            )
            self.position_cap = 0.50
            return "half_cap"

        # 正常
        self.position_cap = 1.0
        return "normal"

    def get_position_cap(self) -> float:
        """返回当前仓位上限系数。"""
        return self.position_cap