"""
一进二打板 (Second Consecutive Limit-up) Momentum Strategy.
Screens for candidates likely to achieve a second consecutive limit-up.
"""

from typing import List, Optional, Tuple

import pandas as pd

from config import Config
from data.market_data import MarketData


class SecondBoardMomentum:
    """
    一进二打板 screener.
    Filters stocks with:
    1. Market cap < 100亿
    2. Limit-up record in past 15 trading days (股性)
    3. Current price > lowest price of the most recent limit-up day (底线防守)
    """

    def __init__(self, market_data: MarketData):
        self.md = market_data
        self._stats: dict = {}

    # ------------------------------------------------------------------
    # Filter 1: Market Cap
    # ------------------------------------------------------------------
    def _check_market_cap(self, code: str) -> bool:
        """Total market cap below 100 billion CNY."""
        cap = self.md.get_market_cap(code)
        return 0 < cap < Config.MOMENTUM.MAX_MARKET_CAP

    # ------------------------------------------------------------------
    # Filters 2+3: Bars-based checks (share a single fetch)
    # ------------------------------------------------------------------
    @staticmethod
    def _find_recent_limit_up(bars: pd.DataFrame) -> Optional[int]:
        """Find the index (in bars) of the most recent limit-up day. Returns None if none."""
        for i in range(len(bars) - 1, 0, -1):
            prev_close = bars.iloc[i - 1]["close"]
            close = bars.iloc[i]["close"]
            if close >= prev_close * 1.095:
                return i
        return None

    def _bars_pass_checks(self, code: str) -> bool:
        """
        Fetch daily bars once, run both limit-up and price-floor checks.
        """
        bars = self.md.get_daily_bars(code, count=Config.MOMENTUM.LIMIT_UP_LOOKBACK_DAYS)
        if bars is None or len(bars) < 2:
            return False

        # Filter 2: has recent limit-up
        limit_up_idx = self._find_recent_limit_up(bars)
        if limit_up_idx is None:
            return False

        # Filter 3: current price > recent limit-up day low
        current_price = self.md.get_price(code)
        limit_up_low = bars.iloc[limit_up_idx]["low"]
        if current_price <= limit_up_low:
            return False

        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self, candidates: List[str]) -> List[str]:
        """
        Run all three filters on candidate stocks (pre-screened pool).
        Returns codes that pass all 一进二打板 conditions.
        """
        qualified: List[str] = []
        self._stats = {"market_cap_fail": 0, "bars_fail": 0, "passed": 0}

        for code in candidates:
            if not self._check_market_cap(code):
                self._stats["market_cap_fail"] += 1
                continue
            if not self._bars_pass_checks(code):
                self._stats["bars_fail"] += 1
                continue
            qualified.append(code)
            self._stats["passed"] += 1

        return qualified