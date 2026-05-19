"""
Market-level Risk Controller (Circuit Breaker).
Monitors extreme market conditions in the first 10 minutes of trading.
"""

from datetime import datetime
from typing import Callable

from config import Config
from data.market_data import MarketData


class MarketRiskController:
    """
    Circuit breaker logic for the first 10 minutes of trading:
    - Declining > 4000 → full liquidation + push alert
    - Declining > 3000 → 50% position cap
    """

    def __init__(self, market_data: MarketData, push_alert_fn: Callable[[str], None] = None):
        self.md = market_data
        self.push_alert = push_alert_fn or (lambda msg: print(f"[ALERT] {msg}"))
        self.position_cap: float = 1.0  # starts at 100%

    # ------------------------------------------------------------------
    # Circuit Breaker Check
    # ------------------------------------------------------------------
    def check_circuit_breaker(self) -> str:
        """
        Check market conditions during the circuit breaker window (09:30-09:40).
        Returns: "full_liquidation", "half_cap", or "normal"
        """
        now = datetime.now().time()
        if not (Config.TRADING_TIME.CIRCUIT_BREAKER_START <= now <= Config.TRADING_TIME.CIRCUIT_BREAKER_END):
            return "normal"

        advancing, declining, flat = self.md.get_market_advancing_declining()

        # Level 1: Extreme — declining > 4000
        if declining > Config.MACRO.CIRCUIT_BREAKER_ADVANCING_BELOW:
            self.push_alert(
                f"[最高级别] 开盘熔断警报！下跌家数 {declining} > 4000，触发全仓一键清仓！"
            )
            self.position_cap = 0.0
            return "full_liquidation"

        # Level 2: Warning — declining > 3000
        if declining > Config.MACRO.CIRCUIT_BREAKER_ADVANCING_WARNING:
            self.position_cap = 0.50
            return "half_cap"

        # Normal
        self.position_cap = 1.0
        return "normal"

    def get_position_cap(self) -> float:
        """Return current position cap from circuit breaker."""
        return self.position_cap