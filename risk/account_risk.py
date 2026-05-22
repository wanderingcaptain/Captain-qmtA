"""
账户级风控 — 追踪连续亏损天数并限制仓位/买入。

变更记录：
  v1.1  - 修复 Bug #1：完整实现 should_suspend_buying()，
          基于 buy_suspended_until 日期追踪暂停期
        - 使用 get_logger 替代 print
"""

from datetime import date
from typing import Optional

from config import Config
from data.portfolio import Portfolio
from utils.logger import get_logger

logger = get_logger("risk.account")


class AccountRiskController:
    """
    账户风控：
    - 连续亏损 2 天 → 仓位上限 50%
    - 连续亏损 3 天 → 强制全仓清仓 + 暂停买入 N 天
    """

    def __init__(self, portfolio: Portfolio):
        self.portfolio = portfolio
        # 暂停买入截止日期（None 表示未暂停）
        self.buy_suspended_until: Optional[date] = None

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def get_consecutive_loss_days(self) -> int:
        """返回当前连续亏损天数。"""
        return self.portfolio.get_consecutive_loss_days()

    def get_position_cap(self) -> float:
        """
        返回仓位上限系数 (0.0 ~ 1.0)。
        0.0 表示强制清仓，0.5 表示半仓上限，1.0 表示无限制。
        """
        loss_days = self.get_consecutive_loss_days()

        if loss_days >= Config.RISK.FORCED_LIQUIDATION_CONSECUTIVE_DAYS:
            return 0.0  # 触发强制清仓

        if loss_days >= Config.RISK.MAX_CONSECUTIVE_LOSS_DAYS:
            logger.warning(
                f"[账户风控] 连续亏损 {loss_days} 天，仓位上限降至 "
                f"{Config.RISK.POSITION_CAP_AFTER_LOSS:.0%}"
            )
            return Config.RISK.POSITION_CAP_AFTER_LOSS

        return 1.0

    # ------------------------------------------------------------------
    # 执行决策
    # ------------------------------------------------------------------
    def should_liquidate_all(self) -> bool:
        """是否需要强制全仓清仓。"""
        loss_days = self.get_consecutive_loss_days()
        if loss_days >= Config.RISK.FORCED_LIQUIDATION_CONSECUTIVE_DAYS:
            logger.critical(
                f"[账户风控] 连续亏损 {loss_days} 天，触发强制清仓！"
            )
            # 设置暂停买入截止日期
            self._set_buy_suspension()
            return True
        return False

    def should_suspend_buying(self) -> bool:
        """
        是否暂停买入。
        强制清仓后，暂停买入 N 天（Config.RISK.BUY_SUSPEND_DAYS）。

        修复 Bug #1：原代码 buy_suspended_until 从未被设置，
        现在由 should_liquidate_all() 调用 _set_buy_suspension() 设置。
        """
        # 先检查是否仍在连续亏损触发条件中
        if self.get_consecutive_loss_days() >= Config.RISK.FORCED_LIQUIDATION_CONSECUTIVE_DAYS:
            return True

        # 检查是否仍在暂停期内
        if self.buy_suspended_until is not None:
            today = date.today()
            if today < self.buy_suspended_until:
                logger.info(
                    f"[账户风控] 买入暂停至 {self.buy_suspended_until}（今天 {today}）"
                )
                return True
            else:
                # 暂停期已过，清除标记
                logger.info(f"[账户风控] 买入暂停期已结束，恢复正常")
                self.buy_suspended_until = None

        return False

    def reset_after_recovery(self):
        """
        盈利日后重置暂停状态。
        连续亏损天数的重置由 Portfolio.snapshot() 自动处理（盈利日 → 归零）。
        此方法仅清除 buy_suspended_until。
        """
        if self.buy_suspended_until is not None and date.today() >= self.buy_suspended_until:
            self.buy_suspended_until = None
            logger.info("[账户风控] 账户恢复正常，买入暂停已解除")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _set_buy_suspension(self):
        """设置买入暂停截止日期。"""
        from datetime import timedelta
        suspend_days = Config.RISK.BUY_SUSPEND_DAYS
        self.buy_suspended_until = date.today() + timedelta(days=suspend_days)
        logger.warning(
            f"[账户风控] 买入暂停 {suspend_days} 天，"
            f"截止至 {self.buy_suspended_until}"
        )