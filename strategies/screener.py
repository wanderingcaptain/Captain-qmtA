"""
Nightly Screener — scans entire A-share universe after hours.
Filters: limit-up pool, volume ratio surge, MA30 volume confirmation, fairy finger.

Flow:
  Phase 0: Get limit-up pool → all limit-up stocks are direct candidates
  Phase 1: Get Sina spot data → filter out ST/科创板/北交所 stocks
  Phase 2: Try EM volume ratios → mark high-ratio stocks as volume candidates
  Phase 3: For candidates, fetch daily bars → MA30 confirmation + fairy finger

ST stocks (名称含 ST/*ST), 科创板 (688xxx), 北交所 (8xxxxx/BJ) are excluded.
"""

from datetime import date, datetime
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from config import Config
from data.market_data import MarketData


class DailyScreener:
    """
    Post-market stock screening engine.
    Scans 5000+ A-share stocks and builds the core watchlist.
    """

    def __init__(self, market_data: MarketData):
        self.md = market_data
        self._excluded_codes: Set[str] = set()
        self._stats: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Exclusion filters
    # ------------------------------------------------------------------
    @staticmethod
    def _is_excluded(code: str, name: str) -> bool:
        """Check if a stock should be excluded from screening."""
        # ST stocks (ST, *ST)
        if "ST" in name or "*ST" in name:
            return True
        # 科创板 (688xxx, 689xxx)
        raw = code.replace("sh", "").replace("sz", "").replace("bj", "")
        if raw.startswith("688") or raw.startswith("689"):
            return True
        # 北交所 (8xxxxx, bj prefix)
        if code.startswith("bj") or raw.startswith("8"):
            return True
        return False

    # ------------------------------------------------------------------
    # Phase 0: Limit-up pool (fast batch)
    # ------------------------------------------------------------------
    def _get_limit_up_candidates(self) -> Set[str]:
        """
        Get today's limit-up pool. All go directly into candidates.
        """
        today_str = date.today().strftime("%Y%m%d")
        try:
            df = self.md.get_limit_up_pool(trade_date=today_str)
            if df.empty:
                return set()
            # Filter out excluded stocks from limit-up pool too
            valid = set()
            for _, row in df.iterrows():
                code = row["code"]
                name = row["name"]
                if self._is_excluded(code, name):
                    self._excluded_codes.add(code)
                    continue
                valid.add(code)
            return valid
        except Exception as e:
            print(f"  [Warn] Limit-up pool fetch failed: {e}")
            return set()

    # ------------------------------------------------------------------
    # Phase 1: Spot-level pre-screening + exclusion (fast memory op)
    # ------------------------------------------------------------------
    def _prepare_spot_index(self) -> pd.DataFrame:
        """
        Get Sina spot data, filter out excluded stocks.
        Returns a DataFrame with code, name, price, volume, pct_chg.
        """
        spot = self.md._get_spot()
        if spot.empty:
            return spot

        # Mark exclusions
        exclude_mask = spot.apply(
            lambda r: self._is_excluded(r["code"], r["name"]), axis=1
        )
        self._excluded_codes.update(spot.loc[exclude_mask, "code"].tolist())

        # Return non-excluded stocks only
        return spot[~exclude_mask].copy()

    # ------------------------------------------------------------------
    # Phase 2: Volume ratio / activity pre-filter
    # ------------------------------------------------------------------
    def _get_volume_ratio_candidates(self, spot: pd.DataFrame) -> Set[str]:
        """
        Best-effort: fetch EM volume ratios.
        If EM is unreachable, warn the user and return empty set.
        """
        try:
            em = self.md._get_em_spot_volume_ratios()
            if em.empty:
                print("  [Warn] EM volume ratio API returned empty — skipping volume pre-filter")
                return set()
        except Exception as e:
            print(f"  [Warn] EM volume ratio API unreachable — {e}")
            print("  [Warn] Skipping volume ratio pre-filter (Phase 3 will still check daily bars)")
            return set()

        candidates: Set[str] = set()
        for _, row in em.iterrows():
            em_code = row["code"]
            vol_ratio = row["volume_ratio"]
            if vol_ratio is None or vol_ratio <= Config.SCREENER.VOLUME_RATIO_THRESHOLD:
                continue
            match = spot[spot["code"].str.endswith(em_code)]
            if not match.empty:
                candidates.add(str(match.iloc[0]["code"]))
        return candidates

    # ------------------------------------------------------------------
    # Phase 3: Daily bars checks (MA30 volume + fairy finger)
    # ------------------------------------------------------------------
    def _check_volume_surge(self, code: str) -> bool:
        """Check if today's volume > 2× MA30 volume."""
        bars = self.md.get_daily_bars(code, count=Config.SCREENER.VOLUME_SURGE_MA_PERIOD + 5)
        if bars is None or len(bars) < Config.SCREENER.VOLUME_SURGE_MA_PERIOD + 1:
            return False

        today_vol = bars.iloc[-1]["volume"]
        ma_vol = bars.iloc[-(Config.SCREENER.VOLUME_SURGE_MA_PERIOD + 1): -1]["volume"].mean()
        if ma_vol <= 0:
            return False
        return today_vol >= ma_vol * Config.SCREENER.VOLUME_SURGE_MULTIPLE

    def _check_fairy_finger(self, code: str) -> bool:
        """
        仙人指路: upper shadow > 2× body, lower shadow < 0.2× body, volume up.
        """
        bars = self.md.get_daily_bars(code, count=10)
        if bars is None or len(bars) < 3:
            return False

        today = bars.iloc[-1]
        yesterday = bars.iloc[-2]

        body = abs(today["open"] - today["close"])
        if body == 0:
            return False

        upper_shadow = today["high"] - max(today["open"], today["close"])
        lower_shadow = min(today["open"], today["close"]) - today["low"]

        if upper_shadow <= Config.SCREENER.UPPER_SHADOW_MIN_RATIO * body:
            return False
        if lower_shadow >= Config.SCREENER.LOWER_SHADOW_MAX_RATIO * body:
            return False
        if today["volume"] <= yesterday["volume"]:
            return False
        return True

    def _check_recent_limit_up(self, code: str) -> bool:
        """Check if stock had a limit-up in the past N days (via daily bars)."""
        bars = self.md.get_daily_bars(code, count=Config.SCREENER.LIMIT_UP_LOOKBACK_DAYS)
        if bars is None or len(bars) < 2:
            return False
        for i in range(1, len(bars)):
            if bars.iloc[i]["close"] >= bars.iloc[i - 1]["close"] * 1.095:
                return True
        return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> List[str]:
        """
        Run full screening pipeline.
        Returns list of candidate stock codes (no exchange prefix).
        """
        self._excluded_codes = set()
        self._stats = {"limit_up": 0, "volume_ratio": 0, "daily_confirmed": 0, "fairy_finger": 0, "errors": 0}

        print(f"  [Phase 0] Fetching limit-up pool...")
        limit_up_set = self._get_limit_up_candidates()
        self._stats["limit_up"] = len(limit_up_set)
        candidates: Set[str] = set(limit_up_set)

        print(f"  [Phase 1] Loading spot data ({len(limit_up_set)} limit-up + rest)...")
        spot = self._prepare_spot_index()
        remaining = len(spot) - len(limit_up_set)
        if remaining <= 0:
            print(f"  All {len(spot)} non-excluded stocks already in limit-up pool.")
            return sorted(candidates)

        print(f"  [Phase 2] Checking volume ratios for {remaining} stocks...")
        vol_candidates = self._get_volume_ratio_candidates(spot)
        self._stats["volume_ratio"] = len(vol_candidates)
        print(f"    Volume ratio > {Config.SCREENER.VOLUME_RATIO_THRESHOLD}: {len(vol_candidates)}")

        # Remove codes already in candidates (limit-up)
        vol_candidates -= candidates

        # Daily bars checks: only run for volume_ratio candidates + random sample
        # to avoid 5000 HTTP requests
        to_check: Set[str] = vol_candidates.copy()
        print(f"  [Phase 3] Daily bars checks for {len(to_check)} stocks...")

        processed = 0
        start_time = datetime.now()
        for code_sina in to_check:
            try:
                # get_daily_bars works with both prefixed and unprefixed codes
                limit_up_ok = self._check_recent_limit_up(code_sina)
                if limit_up_ok:
                    candidates.add(self._strip_prefix(code_sina))
                    self._stats["daily_confirmed"] += 1
                    continue

                surge_ok = self._check_volume_surge(code_sina)
                if surge_ok:
                    candidates.add(self._strip_prefix(code_sina))
                    self._stats["daily_confirmed"] += 1
                    continue

                finger_ok = self._check_fairy_finger(code_sina)
                if finger_ok:
                    candidates.add(self._strip_prefix(code_sina))
                    self._stats["fairy_finger"] += 1

            except Exception as e:
                self._stats["errors"] += 1

            processed += 1
            if processed % Config.SCREENER.LOG_INTERVAL == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = processed / elapsed if elapsed > 0 else 0
                print(f"    Progress: {processed}/{len(to_check)} ({rate:.1f}/s) | "
                      f"candidates: {len(candidates)} | errors: {self._stats['errors']}")

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"  Done: {len(candidates)} candidates in {elapsed:.0f}s "
              f"(limit_up={self._stats['limit_up']}, confirmed={self._stats['daily_confirmed']}, "
              f"fairy={self._stats['fairy_finger']}, errors={self._stats['errors']})")

        return sorted(candidates)

    @staticmethod
    def _strip_prefix(code: str) -> str:
        """Remove exchange prefix from code (sh600519 → 600519)."""
        for prefix in ("sh", "sz", "bj"):
            if code.startswith(prefix):
                return code[len(prefix):]
        return code