"""
Nightly Engine — Post-market Offline Screening.
Runs after market close to screen all A-shares and build the
next day's core monitoring watchlist.
"""

import json
import os
from datetime import datetime, date
from typing import List

from config import Config
from data.market_data import MarketData
from strategies.screener import DailyScreener
from strategies.momentum import SecondBoardMomentum


class NightlyEngine:
    """
    Runs after-hours to:
    1. Screen all A-shares via DailyScreener (异动/形态)
    2. Apply 一进二打板 momentum filter
    3. Persist the core watchlist for next-day intraday monitoring
    """

    def __init__(self, market_data: MarketData):
        self.md = market_data
        self.screener = DailyScreener(market_data)
        self.momentum = SecondBoardMomentum(market_data)
        self.watchlist: List[str] = []
        self.momentum_pool: List[str] = []

    def run(self) -> dict:
        """
        Execute the full nightly screening pipeline.
        Returns a summary dict with counts.
        """
        t0 = datetime.now()
        print(f"[NightlyEngine] Starting nightly screening at {t0}")

        # Step 1: broad screen
        raw_candidates = self.screener.run()
        t1 = datetime.now()
        print(f"[NightlyEngine] Broad screen passed: {len(raw_candidates)} stocks ({(t1 - t0).total_seconds():.0f}s)")

        # Step 2: 一进二打板 momentum
        momentum_candidates = self.momentum.run(raw_candidates)
        t2 = datetime.now()
        print(f"[NightlyEngine] 一进二打板 candidates: {len(momentum_candidates)} stocks ({(t2 - t1).total_seconds():.0f}s)")

        # Step 3: build watchlist (deduplicate)
        self.watchlist = list(set(raw_candidates))
        self.momentum_pool = list(set(momentum_candidates))

        # Step 4: persist
        self._save_watchlist()

        total_elapsed = (datetime.now() - t0).total_seconds()
        summary = {
            "date": str(date.today()),
            "watchlist_count": len(self.watchlist),
            "momentum_count": len(self.momentum_pool),
            "watchlist": self.watchlist,
            "momentum_pool": self.momentum_pool,
            "elapsed_seconds": total_elapsed,
        }
        return summary

    def _save_watchlist(self):
        """Persist watchlist to JSON for the intraday engine."""
        filepath = Config.SYSTEM.WATCHLIST_FILE
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(
                {
                    "date": str(date.today()),
                    "watchlist": self.watchlist,
                    "momentum_pool": self.momentum_pool,
                },
                f,
                indent=2,
            )
        print(f"[NightlyEngine] Watchlist saved to {filepath}")

    def load_watchlist(self) -> List[str]:
        """Load previously saved watchlist."""
        filepath = Config.SYSTEM.WATCHLIST_FILE
        if not os.path.exists(filepath):
            return []
        with open(filepath) as f:
            data = json.load(f)
        self.watchlist = data.get("watchlist", [])
        self.momentum_pool = data.get("momentum_pool", [])
        return self.watchlist