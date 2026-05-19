"""
Sell Logic — Intraday sell / exit signal detection.
Includes stop-loss state machine, take-profit, resistance, divergence, daily breakdown.
"""

from datetime import datetime
from typing import Optional

import pandas as pd

from config import Config
from data.market_data import MarketData
from data.portfolio import PositionState


class SellSignal:
    """
    Evaluates sell signals for each open position.
    Maintains per-position state via PositionState.
    """

    def __init__(self, market_data: MarketData):
        self.md = market_data

    # ------------------------------------------------------------------
    # 1. Stop-loss：price < VWAP * 0.99
    # ------------------------------------------------------------------
    def check_stop_loss(self, pos: PositionState) -> bool:
        """Dynamic stop-loss anchored to entry VWAP."""
        current_price = self.md.get_price(pos.code)
        if current_price <= 0:
            return False
        threshold = pos.vwap_at_entry * (1 - Config.SELL.STOP_LOSS_VWAP_PCT)
        return current_price < threshold

    # ------------------------------------------------------------------
    # 2. Take-profit state machine
    # ------------------------------------------------------------------
    def check_take_profit(self, pos: PositionState) -> Optional[float]:
        """
        Returns sell ratio (0.0–1.0) if take-profit level is hit.
        - +3%: sell 50%
        - +5%: sell remaining 50%
        """
        current_price = self.md.get_price(pos.code)
        gain_pct = (current_price - pos.entry_price) / pos.entry_price

        ratio = 0.0

        # Level 2 (+5%)
        tp2 = Config.SELL.TAKE_PROFIT_2_PCT
        if gain_pct >= tp2 and not pos.take_profit_2_done:
            ratio = Config.SELL.TAKE_PROFIT_2_RATIO
            pos.take_profit_2_done = True
            return ratio

        # Level 1 (+3%) — only if level 2 not already triggered
        tp1 = Config.SELL.TAKE_PROFIT_1_PCT
        if gain_pct >= tp1 and not pos.take_profit_1_done:
            ratio = Config.SELL.TAKE_PROFIT_1_RATIO
            pos.take_profit_1_done = True
            return ratio

        return None

    # ------------------------------------------------------------------
    # 3. Intraday resistance (遇阻)
    # ------------------------------------------------------------------
    def check_resistance(self, pos: PositionState) -> bool:
        """
        If high touches VWAP/开盘价 ±0.5% band but consecutive closes
        fall below VWAP, increment counter. At counter limit → sell.
        """
        current_price = self.md.get_price(pos.code)
        vwap = self.md.get_vwap(pos.code)
        band = Config.SELL.RESISTANCE_VWAP_BAND_PCT

        # Check if high has touched the VWAP band
        bars = self.md.get_minute_bars(pos.code)
        if bars is None or len(bars) < 2:
            return False

        last_two = bars.tail(2)
        vwap_lower = vwap * (1 - band)
        vwap_upper = vwap * (1 + band)

        # Has high touched the band?
        touched_band = last_two["high"].max() >= vwap_lower
        if not touched_band:
            return False

        # Both closes below VWAP?
        closes_below = (last_two["close"] < vwap).sum()
        if closes_below >= Config.SELL.RESISTANCE_CONSECUTIVE_BARS:
            pos.resistance_counter += 1

        return pos.resistance_counter >= Config.SELL.RESISTANCE_COUNTER_LIMIT

    # ------------------------------------------------------------------
    # 4. Volume-price divergence (量价背离)
    # ------------------------------------------------------------------
    def check_divergence(self, pos: PositionState) -> bool:
        """
        Volume ratio > 10 AND gain in [1%, 2.5%] for > 5 min → sell.
        """
        vol_ratio = self.md.get_volume_ratio(pos.code)
        if vol_ratio <= Config.SELL.DIVERGENCE_VOLUME_RATIO_THRESHOLD:
            pos.divergence_start_time = None
            return False

        current_price = self.md.get_price(pos.code)
        gain_pct = (current_price - pos.entry_price) / pos.entry_price

        if not (Config.SELL.DIVERGENCE_GAIN_MIN_PCT <= gain_pct <= Config.SELL.DIVERGENCE_GAIN_MAX_PCT):
            pos.divergence_start_time = None
            return False

        # Start or continue tracking duration
        if pos.divergence_start_time is None:
            pos.divergence_start_time = datetime.now()
            return False

        elapsed = (datetime.now() - pos.divergence_start_time).total_seconds()
        return elapsed >= Config.SELL.DIVERGENCE_DURATION_MINUTES * 60

    # ------------------------------------------------------------------
    # 5. Daily breakdown (昨日台阶理论)
    # ------------------------------------------------------------------
    def check_daily_breakdown(self, code: str) -> bool:
        """
        At 14:50: if current price < min(yesterday close, day-before close) → sell.
        """
        now = datetime.now().time()
        if now < Config.SELL.BREAKDOWN_CHECK_TIME:
            return False

        current_price = self.md.get_price(code)

        # Get yesterday's and day-before's close
        bars = self.md.get_daily_bars(code, count=5)
        if bars is None or len(bars) < 3:
            return False

        yesterday_close = bars.iloc[-2]["close"]
        day_before_close = bars.iloc[-3]["close"]
        floor = min(yesterday_close, day_before_close)

        return current_price < floor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def evaluate_all(self, pos: PositionState) -> str:
        """
        Run all sell checks. Returns sell signal reason string
        or empty string if no sell condition is met.

        Priority: stop_loss > take_profit > resistance > divergence > breakdown
        """
        if self.check_stop_loss(pos):
            return "stop_loss"

        tp_ratio = self.check_take_profit(pos)
        if tp_ratio:
            return f"take_profit:{tp_ratio}"

        if self.check_resistance(pos):
            return "resistance"

        if self.check_divergence(pos):
            return "divergence"

        if self.check_daily_breakdown(pos.code):
            return "daily_breakdown"

        return ""