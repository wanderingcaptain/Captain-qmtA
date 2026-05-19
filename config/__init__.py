"""
A-Share Quantitative Trading System - Configuration Module
All configurable parameters are centralized here for easy tuning.
"""

from datetime import time
from typing import Dict, List, Optional


# ============================================================
# Market Trading Hours
# ============================================================
class TradingTime:
    """Trading session time constants"""
    MORNING_OPEN = time(9, 30)
    MORNING_CLOSE = time(11, 30)
    AFTERNOON_OPEN = time(13, 0)
    AFTERNOON_CLOSE = time(15, 0)

    # Intraday buy time windows
    BUY_WINDOW_1_START = time(9, 30)
    BUY_WINDOW_1_END = time(10, 40)
    BUY_WINDOW_2_START = time(14, 40)
    BUY_WINDOW_2_END = time(14, 55)

    # Circuit breaker window (first 10 minutes after open)
    CIRCUIT_BREAKER_START = time(9, 30)
    CIRCUIT_BREAKER_END = time(9, 40)

    # Daily breakdown check (close to market close)
    DAILY_BREAKDOWN_CHECK = time(14, 50)


# ============================================================
# Macro Market Sentiment Thresholds
# ============================================================
class MacroFilter:
    """Macro-level market sentiment parameters"""
    # Number of advancing stocks required to allow buying
    ADVANCING_STOCKS_THRESHOLD: int = 3000

    # Circuit breaker: extreme bearish thresholds (advancing < threshold)
    CIRCUIT_BREAKER_ADVANCING_BELOW: int = 4000   # Full liquidation
    CIRCUIT_BREAKER_ADVANCING_WARNING: int = 3000  # 50% position cap


# ============================================================
# Buy Strategy Parameters
# ============================================================
class BuyParams:
    """Micro-level buy signal parameters"""
    # VWAP support tolerance band (± %)
    VWAP_BAND_PERCENT: float = 0.005  # 0.5%

    # Confirmation period: number of consecutive minutes close must hold above VWAP
    VWAP_CONFIRM_MINUTES: int = 3

    # Volume shrinkage: T-minute volume < threshold × avg volume of past N minutes
    VOLUME_SHRINK_RATIO: float = 0.50   # 50% of average
    VOLUME_LOOKBACK_MINUTES: int = 5

    # Max concurrent open positions (buy logic stops when full)
    MAX_OPEN_POSITIONS: int = 5

    # Rapid rally cooling: price surge threshold
    RAPID_RALLY_PRICE_PCT: float = 0.03        # 3% in 3 minutes
    RAPID_RALLY_VOLUME_MULTIPLE: float = 3.0    # 3× early-session average volume
    RAPID_RALLY_LOOKBACK_MINUTES: int = 3
    COOLING_PERIOD_MINUTES: int = 10

    # Early session volume baseline (first N minutes used for baseline calculation)
    EARLY_SESSION_BASELINE_MINUTES: int = 30


# ============================================================
# Sell Strategy Parameters
# ============================================================
class SellParams:
    """Sell / exit signal parameters"""
    # Stop-loss: price < VWAP × (1 - STOP_LOSS_PCT)
    STOP_LOSS_VWAP_PCT: float = 0.01  # 1% below VWAP

    # Take-profit partial exits
    TAKE_PROFIT_1_PCT: float = 0.03   # 3% → sell 50%
    TAKE_PROFIT_1_RATIO: float = 0.50
    TAKE_PROFIT_2_PCT: float = 0.05   # 5% → sell remaining 50%
    TAKE_PROFIT_2_RATIO: float = 0.50

    # Intraday resistance: consecutive closes below VWAP
    RESISTANCE_VWAP_BAND_PCT: float = 0.005  # 0.5%
    RESISTANCE_CONSECUTIVE_BARS: int = 2
    RESISTANCE_COUNTER_LIMIT: int = 2

    # Volume-price divergence
    DIVERGENCE_VOLUME_RATIO_THRESHOLD: float = 10.0
    DIVERGENCE_GAIN_MIN_PCT: float = 0.01   # 1%
    DIVERGENCE_GAIN_MAX_PCT: float = 0.025  # 2.5%
    DIVERGENCE_DURATION_MINUTES: int = 5

    # Daily breakdown (yesterday's step theory)
    BREAKDOWN_CHECK_TIME = time(14, 50)


# ============================================================
# Risk Control Parameters
# ============================================================
class RiskParams:
    """Account-level and market-level risk control"""
    # Consecutive loss limits
    MAX_CONSECUTIVE_LOSS_DAYS: int = 2
    POSITION_CAP_AFTER_LOSS: float = 0.50  # 50% position cap

    FORCED_LIQUIDATION_CONSECUTIVE_DAYS: int = 3
    BUY_SUSPEND_DAYS: int = 1


# ============================================================
# Nightly Screener Parameters
# ============================================================
class ScreenerParams:
    """Nightly stock screening parameters"""
    # Volume surge: volume ratio from spot data
    VOLUME_RATIO_THRESHOLD: float = 2.5   # 量比 > 2.5 为显著放量

    # Volume surge: today volume > MULTIPLE × 30-day MA volume
    VOLUME_SURGE_MULTIPLE: float = 2.0
    VOLUME_SURGE_MA_PERIOD: int = 30

    # 仙人指路 (Fairy's Finger / long upper shadow)
    SCREENING_LOOKBACK_DAYS: int = 20
    LIMIT_UP_LOOKBACK_DAYS: int = 20

    UPPER_SHADOW_MIN_RATIO: float = 2.0   # H_upper > 2 × H_body
    LOWER_SHADOW_MAX_RATIO: float = 0.2   # H_lower < 0.2 × H_body

    # Progress logging interval
    LOG_INTERVAL: int = 500   # log every N stocks


# ============================================================
# 一进二打板 (Second-board Momentum) Parameters
# ============================================================
class MomentumParams:
    """Second consecutive limit-up screening parameters"""
    MAX_MARKET_CAP: float = 10_000_000_000  # 10 billion (100亿)
    LIMIT_UP_LOOKBACK_DAYS: int = 15
    # Current price must be > lowest price of the most recent limit-up day


# ============================================================
# System / Runtime Configuration
# ============================================================
class SystemConfig:
    """System behavior configuration"""
    DATA_FETCH_INTERVAL_SECONDS: int = 60  # Minute-level data refresh
    POSITION_FILE: str = "data/positions.json"
    ACCOUNT_FILE: str = "data/account.json"
    LOG_DIR: str = "logs"
    LOG_LEVEL: str = "INFO"

    # Push notification (placeholder)
    NOTIFICATION_ENABLED: bool = True
    NOTIFICATION_CHANNEL: str = "console"  # Options: console, pushover, wechat, dingtalk

    # Stock universe
    STOCK_UNIVERSE: str = "A"  # All A-shares
    WATCHLIST_FILE: str = "data/watchlist.json"


# ============================================================
# Consolidated config object (convenience accessor)
# ============================================================
class Config:
    """Top-level configuration namespace"""
    TRADING_TIME = TradingTime()
    MACRO = MacroFilter()
    BUY = BuyParams()
    SELL = SellParams()
    RISK = RiskParams()
    SCREENER = ScreenerParams()
    MOMENTUM = MomentumParams()
    SYSTEM = SystemConfig()