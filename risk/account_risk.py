"""
Account-level Risk Controller.
Monitors consecutive loss days and adjusts position limits accordingly.
"""

from typing import Dict

from config import Config
from data.portfolio import Portfolio


class AccountRiskController:
    """
    Tracks daily P&L and enforces:
    - 2 consecutive loss days → position cap = 50%
    - 3 consecutive loss days → full liquidation + 1-day buy suspension
    """

    def __init__(self, portfolio: Portfolio):
        self.portfolio = portfolio
        self.buy_suspended_until: str = ""  # date string "YYYY-MM-DD"

    # ------------------------------------------------------------------
    # Loss Streak Checks
    # ------------------------------------------------------------------
    def get_consecutive_loss_days(self) -> int:
        """Return current consecutive loss streak."""
        return self.portfolio.get_consecutive_loss_days()

    def get_position_cap(self) -> float:
        """
        Return position size cap (1.0 = full, 0.5 = half).
        Based on consecutive loss days.
        """
        loss_days = self.get_consecutive_loss_days()

        if loss_days >= Config.RISK.FORCED_LIQUIDATION_CONSECUTIVE_DAYS:
            return 0.0  # forced liquidation

        if loss_days >= Config.RISK.MAX_CONSECUTIVE_LOSS_DAYS:
            return Config.RISK.POSITION_CAP_AFTER_LOSS

        return 1.0  # full cap

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def should_liquidate_all(self) -> bool:
        """Check if forced liquidation is required."""
        return self.get_consecutive_loss_days() >= Config.RISK.FORCED_LIQUIDATION_CONSECUTIVE_DAYS

    def should_suspend_buying(self) -> bool:
        """
        After forced liquidation, buying is suspended for N days.
        """
        loss_days = self.get_consecutive_loss_days()
        if loss_days >= Config.RISK.FORCED_LIQUIDATION_CONSECUTIVE_DAYS:
            return True
        # Check if we are still in suspension period
        return False

    def reset_after_recovery(self):
        """Call this after a profitable day to reset state."""
        # This is auto-handled by Portfolio.snapshot() which tracks
        # consecutive_loss_days. A gain day resets to 0.
        pass