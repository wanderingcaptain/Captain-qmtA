"""
A-Share Quantitative Trading System
QMT_THS v1.0

Usage:
    python main.py nightly    # Run nightly screening
    python main.py intraday   # Run intraday monitoring
    python main.py            # Run both (screening first, then intraday)
"""

import sys

from config import Config
from data.market_data import MarketData
from data.portfolio import Portfolio
from core.nightly_engine import NightlyEngine
from core.intraday_engine import IntradayEngine
from utils.logger import setup_logger

logger = setup_logger("qmt_ths")


def run_nightly() -> dict:
    """Execute the nightly offline screening."""
    logger.info("=" * 50)
    logger.info("Starting Nightly Screening Engine...")
    logger.info("=" * 50)

    md = MarketData()
    engine = NightlyEngine(md)
    summary = engine.run()

    logger.info(f"Watchlist size: {summary['watchlist_count']}")
    logger.info(f"Momentum pool size: {summary['momentum_count']}")
    logger.info("Nightly screening complete.")
    return summary


def run_intraday():
    """Execute the intraday monitoring loop."""
    logger.info("=" * 50)
    logger.info("Starting Intraday Monitoring Engine...")
    logger.info("=" * 50)

    md = MarketData()
    portfolio = Portfolio()
    engine = IntradayEngine(md, portfolio)

    # Load watchlist from nightly results
    nightly = NightlyEngine(md)
    watchlist = nightly.load_watchlist()
    engine.load_watchlist(watchlist)

    if not watchlist:
        logger.warning("No watchlist available. Run nightly screening first.")
        return

    logger.info(f"Monitoring {len(watchlist)} stocks in real-time.")
    engine.start()


def main():
    if len(sys.argv) < 2:
        # Default: run both
        logger.info("No mode specified. Running nightly → intraday sequence.")
        run_nightly()
        if MarketData.is_trading_time():
            run_intraday()
        else:
            logger.info("Outside trading hours. Skipping intraday mode.")
        return

    mode = sys.argv[1].lower()

    if mode == "nightly":
        run_nightly()

    elif mode == "intraday":
        run_intraday()

    elif mode in ("--help", "-h"):
        print("Usage: python main.py [nightly|intraday]")
        print("  nightly   — Run post-market offline screening")
        print("  intraday  — Run real-time intraday monitoring")
        print("  (default) — Run nightly → intraday sequence")

    else:
        print(f"Unknown mode: {mode}. Use --help for usage.")
        sys.exit(1)


if __name__ == "__main__":
    main()