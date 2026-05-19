"""
Buy Logic — Intraday buy signal detection.
Three-layer filter: macro sentiment → time window → micro VWAP pattern.
"""

from datetime import datetime, time
from typing import Optional

import pandas as pd

from config import Config
from data.market_data import MarketData


class BuySignal:
    """
    Evaluates buy signals for stocks in the core watchlist.
    All three filters must pass before a buy is triggered.
    """

    def __init__(self, market_data: MarketData):
        self.md = market_data
        self._cooling_map: dict = {}  # code → cooling_until (datetime)

    # ------------------------------------------------------------------
    # Layer 1: Macro Sentiment Filter
    # ------------------------------------------------------------------
    def _check_macro_sentiment(self) -> bool:
        """
        Check if advancing stocks >= threshold.
        If not, block all buy signals.
        """
        advancing, declining, flat = self.md.get_market_advancing_declining()
        return advancing >= Config.MACRO.ADVANCING_STOCKS_THRESHOLD

    # ------------------------------------------------------------------
    # Layer 2: Time Window Filter
    # ------------------------------------------------------------------
    @staticmethod
    def _check_time_window() -> bool:
        """
        Buy only allowed during:
         09:30 < T < 10:40  OR  14:40 < T < 14:55
        """
        now = datetime.now().time()
        w1s = Config.TRADING_TIME.BUY_WINDOW_1_START
        w1e = Config.TRADING_TIME.BUY_WINDOW_1_END
        w2s = Config.TRADING_TIME.BUY_WINDOW_2_START
        w2e = Config.TRADING_TIME.BUY_WINDOW_2_END
        return (w1s <= now <= w1e) or (w2s <= now <= w2e)

    # ------------------------------------------------------------------
    # Layer 3: VWAP Support Pattern (Micro)
    # ------------------------------------------------------------------
    def _check_vwap_support(self, code: str) -> bool:
        """
        VWAP support pattern:
        1. Low of minute T is within ±0.5% of VWAP
        2. Next 3-minute closes all above VWAP
        3. Volume at minute T < 50% of past 5-min avg volume (缩量)
        4. Not in a cooling period (急拉不买)
        """
        # Reject if in cooling period
        if self._in_cooling(code):
            return False

        bars = self.md.get_minute_bars(code)
        if bars is None or len(bars) < 10:
            return False

        vwap = self.md.get_vwap(code)
        vwap_lower = vwap * (1 - Config.BUY.VWAP_BAND_PERCENT)
        vwap_upper = vwap * (1 + Config.BUY.VWAP_BAND_PERCENT)

        # Iterate from latest bar backward to find support touch
        for i in range(len(bars) - 1, max(len(bars) - 20, 0), -1):
            t_bar = bars.iloc[i]
            low_t = t_bar["low"]

            # Condition 1: low touches VWAP band
            if not (vwap_lower <= low_t <= vwap_upper):
                continue

            # Condition 2: next N minutes close above VWAP
            conf = Config.BUY.VWAP_CONFIRM_MINUTES
            if i + conf >= len(bars):
                continue
            holds = all(
                bars.iloc[j]["close"] >= vwap
                for j in range(i + 1, i + conf + 1)
            )
            if not holds:
                continue

            # Condition 3: volume shrinkage
            vol_t = t_bar["volume"]
            avg_vol = bars.iloc[i - Config.BUY.VOLUME_LOOKBACK_MINUTES : i]["volume"].mean()
            if avg_vol > 0 and vol_t / avg_vol >= Config.BUY.VOLUME_SHRINK_RATIO:
                continue  # not enough shrinkage

            # Condition 4: check for rapid rally (急拉)
            self._check_rapid_rally(code, bars, i)

            return True

        return False

    # ------------------------------------------------------------------
    # Rapid Rally Cool-down (急拉不买)
    # ------------------------------------------------------------------
    def _check_rapid_rally(self, code: str, bars: pd.DataFrame, current_idx: int):
        """
        If price surged > 3% in past 3 min with volume > 3× early avg,
        set a 10-min cooling period.
        """
        if current_idx < Config.BUY.RAPID_RALLY_LOOKBACK_MINUTES:
            return

        near = bars.iloc[current_idx - Config.BUY.RAPID_RALLY_LOOKBACK_MINUTES : current_idx + 1]
        price_change = (near.iloc[-1]["close"] - near.iloc[0]["open"]) / near.iloc[0]["open"]

        if price_change < Config.BUY.RAPID_RALLY_PRICE_PCT:
            return

        # Volume check: compare to early-session average
        all_bars = bars
        if len(all_bars) < Config.BUY.EARLY_SESSION_BASELINE_MINUTES:
            return
        early_bars = all_bars.head(Config.BUY.EARLY_SESSION_BASELINE_MINUTES)
        early_avg_vol = early_bars["volume"].mean() if not early_bars.empty else 1
        surge_vol = near["volume"].mean()

        if surge_vol > early_avg_vol * Config.BUY.RAPID_RALLY_VOLUME_MULTIPLE:
            self._cooling_map[code] = datetime.now()

    def _in_cooling(self, code: str) -> bool:
        """Check if stock is in cooling period."""
        until = self._cooling_map.get(code)
        if until is None:
            return False
        elapsed = (datetime.now() - until).total_seconds()
        if elapsed > Config.BUY.COOLING_PERIOD_MINUTES * 60:
            del self._cooling_map[code]
            return False
        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def evaluate(self, code: str) -> bool:
        """
        Full buy signal pipeline: macro → time → micro.
        All must pass. Returns True if conditions to buy are met.
        """
        if not self._check_macro_sentiment():
            return False
        if not self._check_time_window():
            return False
        return self._check_vwap_support(code)