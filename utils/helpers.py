"""
Helper utilities.
"""

from typing import Optional

from data.market_data import MarketData


def is_trading_day() -> bool:
    """Check if today is a valid A-share trading day."""
    return MarketData.is_market_open_today()


def calc_position_size(
    cash: float,
    price: float,
    cap: float = 1.0,
    max_stocks: int = 5,
) -> int:
    """
    Calculate position size per stock.
    Returns number of shares (rounded to 100-share lots).
    """
    per_stock_cash = cash * cap / max_stocks
    shares = int(per_stock_cash / price)
    return round_lot(shares)


def round_lot(shares: int) -> int:
    """
    Round down to nearest 100-share lot (A-share convention).
    """
    return (shares // 100) * 100