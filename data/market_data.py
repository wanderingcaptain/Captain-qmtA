"""
Market Data Layer — akshare wrapper with English method names.
All data-fetching logic is centralized here.

NOTE: Uses Sina backend (stock_zh_a_spot, stock_zh_a_daily, stock_zh_a_minute)
as the primary source since East Money curl_cffi endpoints fail on Python 3.14.
"""
import akshare_proxy_patch

akshare_proxy_patch.install_patch(
    "101.201.173.125",
    auth_token="202605189JYUMHB0",
    retry=30,
    hook_domains=[
        "push2.eastmoney.com",
    ],
)

from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

import pandas as pd


class MarketData:
    """
    Unified market data interface.
    Wraps akshare (Chinese) functions behind English method names.
    """

    # Class-level caches (used by static methods)
    _adv_dec_df: Optional[pd.DataFrame] = None
    _adv_dec_timestamp: Optional[datetime] = None
    _em_spot_df: Optional[pd.DataFrame] = None
    _em_spot_timestamp: Optional[datetime] = None

    def __init__(self):
        self._spot_df: Optional[pd.DataFrame] = None
        self._spot_timestamp: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Internal: cached spot data (refresh on each call)
    # ------------------------------------------------------------------
    def _get_spot(self) -> pd.DataFrame:
        """
        Fetch and cache the full A-share spot DataFrame from
        Sina API, fetching pages individually with retry on failure.
        Cache is valid for 300 seconds (5 min) to avoid
        re-triggering during a multi-step pipeline run.
        """

        import requests as _requests
        import time as _time

        now = datetime.now()
        if (
            self._spot_df is not None
            and self._spot_timestamp is not None
            and (now - self._spot_timestamp).total_seconds() < 300
        ):
            return self._spot_df

        # 1) Get total page count (with retry)
        count_url = (
            "http://vip.stock.finance.sina.com.cn/quotes_service"
            "/api/json_v2.php/Market_Center.getHQNodeStockCount"
        )
        for attempt in range(3):
            try:
                resp = _requests.get(
                    count_url,
                    params={"node": "hs_a"},
                    headers={"Referer": "https://finance.sina.com.cn"},
                    timeout=15,
                )
                text = resp.text.strip()
                if text.startswith("<"):
                    raise ValueError("Sina 返回 HTML（限流中）")
                total = int(text.strip('"'))
                break
            except Exception:
                if attempt < 2:
                    _time.sleep(3 ** attempt)
        else:
            raise RuntimeError("全市场行情获取失败（Sina 限流），非交易时段重试即可")

        page_count = total // 80 + (1 if total % 80 else 0)

        # 2) Fetch each page with retry
        api_url = (
            "http://vip.stock.finance.sina.com.cn/quotes_service"
            "/api/json_v2.php/Market_Center.getHQNodeData"
        )
        headers = {"Referer": "https://finance.sina.com.cn"}
        all_rows = []
        for page in range(1, page_count + 1):
            params = {
                "page": str(page),
                "num": "80",
                "sort": "symbol",
                "asc": "1",
                "node": "hs_a",
                "symbol": "",
                "_s_r_a": "page",
            }
            for attempt in range(3):
                try:
                    r = _requests.get(
                        api_url, params=params, headers=headers, timeout=15
                    )
                    data = r.json()
                    all_rows.extend(data)
                    break
                except Exception:
                    if attempt < 2:
                        _time.sleep(1 + attempt)
                    else:
                        # Last resort: skip this page and continue
                        # (don't crash the whole batch for one bad page)
                        pass

        if not all_rows:
            # Fall back to akshare's built-in if our own fetch got nothing
            import akshare as ak

            df = ak.stock_zh_a_spot()
        else:
            df = pd.DataFrame(all_rows)
            # Sina API returns both "symbol" (prefixed) and "code" (bare)
            # Use the bare "code" column; no prefix stripping needed
            df.rename(
                columns={
                    "trade": "price",
                    "changepercent": "pct_chg",
                    "pricechange": "change",
                    "settlement": "prev_close",
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "volume": "volume",
                    "amount": "amount",
                },
                inplace=True,
            )

        self._spot_df = df
        self._spot_timestamp = now
        return df

    def _get_em_spot_volume_ratios(self) -> pd.DataFrame:
        """
        Fetch volume ratios for all A-shares from East Money's push2 API.
        Uses regular requests (not curl_cffi). Cached 60 seconds.
        Returns DataFrame with columns: code (no prefix), volume_ratio.
        """
        now = datetime.now()
        if (
            self._em_spot_df is not None
            and self._em_spot_timestamp is not None
            and (now - self._em_spot_timestamp).total_seconds() < 60
        ):
            return self._em_spot_df

        import requests

        all_rows = []
        page = 1
        page_size = 100  # EM API max items per page
        max_pages = 60    # safety limit (5853 / 100 ≈ 59)

        while page <= max_pages:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": str(page),
                "pz": str(page_size),
                "po": "1",
                "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2",
                "invt": "2",
                "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                "fields": "f2,f3,f10,f12,f14",  # price, pct_chg, volume_ratio, code, name
            }
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            items = data.get("data", {}).get("diff", [])
            if not items:
                break
            for item in items:
                all_rows.append({
                    "code": str(item.get("f12", "")),
                    "name": str(item.get("f14", "")),
                    "price": item.get("f2", 0),
                    "pct_chg": item.get("f3", 0),
                    "volume_ratio": item.get("f10", 0),
                })
            if len(items) < page_size:
                break
            page += 1

        df = pd.DataFrame(all_rows)
        # Ensure numeric types
        for col in ("price", "pct_chg", "volume_ratio"):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        self._em_spot_df = df
        self._em_spot_timestamp = now
        return df

    # ------------------------------------------------------------------
    # Stock Universe & Info
    # ------------------------------------------------------------------
    def get_stock_list(self) -> List[str]:
        """
        Get full A-share stock code list.
        Returns: list of codes, e.g. ["sh600519", "sz000001", ...]
        """
        df = self._get_spot()
        return df["code"].astype(str).tolist()

    def get_stock_info(self, code: str) -> Dict:
        """
        Get metadata for a single stock.
        Returns: dict with name, industry, market_cap, total_shares, etc.

        Primary: Sina daily data (outstanding_share + price = market_cap).
        Fallback: ak.stock_individual_info_em (East Money).
        """
        result = {}

        # Try Sina daily data first (always works)
        try:
            daily = self.get_daily_bars(code, count=1)
            if not daily.empty:
                last = daily.iloc[-1]
                result["最新价"] = last["close"]
                result["流通股本"] = last["outstanding_share"]
                result["流通市值"] = last["close"] * last["outstanding_share"]
        except Exception:
            pass

        # Spot data for name
        try:
            df = self._get_spot()
            row = df[df["code"] == code]
            if not row.empty:
                result["股票简称"] = row.iloc[0]["name"]
                result["股票代码"] = code
        except Exception:
            pass

        # Try EM for extra fields (industry, total shares, etc.)
        try:
            import akshare as ak

            info_df = ak.stock_individual_info_em(code)
            for _, r in info_df.iterrows():
                result[r["item"]] = r["value"]
        except Exception:
            pass

        return result

    def get_market_cap(self, code: str) -> float:
        """Total market capitalization (元)."""
        info = self.get_stock_info(code)
        # Prefer 总市值 from EM, fall back to 流通市值 from Sina
        cap = info.get("总市值", 0)
        if cap:
            return float(cap)
        cap = info.get("流通市值", 0)
        return float(cap)

    # ------------------------------------------------------------------
    # Limit-up Pool (涨停板行情)
    # ------------------------------------------------------------------
    def get_limit_up_pool(self, trade_date: str = None) -> pd.DataFrame:
        """
        Get limit-up pool for a given date from East Money.
        Returns DataFrame with columns: code, name, pct_chg, price, market_cap,
        turnover_rate, seal_amount, first_seal_time, last_seal_time,
        blast_count, limit_up_count, consecutive_boards, industry.

        The API returns codes WITHOUT exchange prefix (e.g. "001259").
        NOTE: EM API requires YYYYMMDD format (no hyphens).
        """
        import akshare as ak

        if trade_date is not None:
            trade_date = trade_date.replace("-", "")
        df = ak.stock_zt_pool_em(date=trade_date)
        if df.empty:
            return df
        df.rename(
            columns={
                "代码": "code",
                "名称": "name",
                "涨跌幅": "pct_chg",
                "最新价": "price",
                "成交额": "amount",
                "流通市值": "float_market_cap",
                "总市值": "total_market_cap",
                "换手率": "turnover_rate",
                "封板资金": "seal_amount",
                "首次封板时间": "first_seal_time",
                "最后封板时间": "last_seal_time",
                "炸板次数": "blast_count",
                "涨停统计": "limit_up_stats",
                "连板数": "consecutive_boards",
                "所属行业": "industry",
            },
            inplace=True,
        )
        return df

    # ------------------------------------------------------------------
    # Daily (K-line) Data
    # ------------------------------------------------------------------
    def get_daily_bars(
        self, code: str, count: int = 60, adjust: str = "qfq"
    ) -> pd.DataFrame:
        """
        Get daily OHLCV bars (Sina backend).
        Returns DataFrame with columns: date, open, high, low, close, volume, amount.
        adjust: "qfq" (前复权), "hfq" (后复权), "" (不复权)
        """
        import akshare as ak

        # Sina daily: code prefix required (sh/sz)
        sina_code = self._to_sina_code(code)
        df = ak.stock_zh_a_daily(sina_code, adjust=adjust)
        if df.empty:
            return df
        # Sina already returns English column names
        return df.tail(count).reset_index(drop=True)

    def get_daily_bar(
        self, code: str, trade_date: date, adjust: str = "qfq"
    ) -> Optional[pd.Series]:
        """Get a single day's bar."""
        df = self.get_daily_bars(code, count=10, adjust=adjust)
        match = df[df["date"] == pd.Timestamp(trade_date)]
        return match.iloc[0] if not match.empty else None

    def get_limit_up_prices(self, code: str, lookback: int = 20) -> pd.DataFrame:
        """
        Get historical limit-up days.
        Returns DataFrame with columns: date, close (limit price).
        """
        df = self.get_daily_bars(code, count=lookback + 5)
        if df.empty:
            return pd.DataFrame()

        limit_ups = []
        for i in range(1, len(df)):
            prev_close = df.iloc[i - 1]["close"]
            close = df.iloc[i]["close"]
            if close >= prev_close * 1.095:
                limit_ups.append(
                    {"date": df.iloc[i]["date"], "close": close}
                )
        return pd.DataFrame(limit_ups)

    # ------------------------------------------------------------------
    # Intraday (Minute/Tick) Data
    # ------------------------------------------------------------------
    def get_minute_bars(self, code: str) -> pd.DataFrame:
        """
        Get today's minute-level bars for a single stock (Sina backend).
        Returns DataFrame with columns: time, open, high, low, close, volume, amount.
        """
        import akshare as ak

        sina_code = self._to_sina_code(code)
        df = ak.stock_zh_a_minute(sina_code, period="1")
        if df.empty:
            return df
        # Sina returns all columns as str; convert to numeric
        df.rename(columns={"day": "time"}, inplace=True)
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def get_current_ask_bid(self, code: str) -> Dict:
        """
        Get current real-time quote (latest price, bid/ask, volume).
        """
        df = self._get_spot()
        row = df[df["code"] == code]
        if row.empty:
            return {}
        row = row.iloc[0]
        return {
            "code": code,
            "price": row["price"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "prev_close": row["prev_close"],
            "volume": row["volume"],
            "amount": row["amount"],
            "pct_chg": row["pct_chg"],
        }

    def get_vwap(self, code: str) -> float:
        """
        Calculate current session VWAP (Volume-Weighted Average Price).
        Formula: cumulative_turnover / cumulative_volume
        """
        bars = self.get_minute_bars(code)
        if bars.empty:
            return 0.0
        total_turnover = bars["amount"].sum()
        total_volume = bars["volume"].sum()
        if total_volume == 0:
            return 0.0
        return total_turnover / total_volume

    def get_price(self, code: str) -> float:
        """Latest traded price."""
        df = self._get_spot()
        row = df[df["code"] == code]
        if row.empty:
            return 0.0
        return float(row.iloc[0]["price"])

    def get_volume_ratio(self, code: str) -> float:
        """
        Volume ratio — Sina spot does not provide this field directly.
        Calculated as: current session avg volume per minute
        / past 5 days avg volume per minute at same time.
        """
        # Approximate: compare today's total volume to 5-day average daily volume
        bars = self.get_minute_bars(code)
        if bars.empty:
            return 0.0
        today_vol = bars["volume"].sum()
        daily_bars = self.get_daily_bars(code, count=6)
        if daily_bars.empty or len(daily_bars) < 2:
            return 0.0
        avg_daily_vol = daily_bars.tail(5)["volume"].mean()
        if avg_daily_vol <= 0:
            return 0.0
        return today_vol / avg_daily_vol

    # ------------------------------------------------------------------
    # Index / Market-wide Data
    # ------------------------------------------------------------------
    @staticmethod
    def get_market_advancing_declining() -> Tuple[int, int, int]:
        """
        Get real-time advancing / declining / flat stock counts.
        Computed from the full A-share spot DataFrame (Sina, cached 30s).
        Returns: (advancing, declining, flat)
        """
        now = datetime.now()
        if (
            MarketData._adv_dec_df is not None
            and MarketData._adv_dec_timestamp is not None
            and (now - MarketData._adv_dec_timestamp).total_seconds() < 30
        ):
            df = MarketData._adv_dec_df
        else:
            import akshare as ak

            df = ak.stock_zh_a_spot()
            MarketData._adv_dec_df = df
            MarketData._adv_dec_timestamp = now

        advancing = int((df["涨跌幅"] > 0).sum())
        declining = int((df["涨跌幅"] < 0).sum())
        flat = int((df["涨跌幅"] == 0).sum())
        return advancing, declining, flat

    def get_index_bars(self, index_code: str = "000001", count: int = 60) -> pd.DataFrame:
        """
        Get index daily bars (e.g., 上证指数 sh000001, 深证成指 sz399001).
        """
        import akshare as ak

        sina_code = self._to_sina_code(index_code)
        df = ak.stock_zh_index_daily(sina_code)
        if df.empty:
            return df
        return df.tail(count).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Historical Volume Average (for volume surge detection)
    # ------------------------------------------------------------------
    def get_volume_ma(self, code: str, period: int = 30) -> float:
        """
        Calculate N-day average volume.
        """
        df = self.get_daily_bars(code, count=period + 5)
        if df.empty or len(df) < period:
            return 0.0
        return df.tail(period)["volume"].mean()

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    @staticmethod
    def _to_sina_code(code: str) -> str:
        """
        Convert raw code to Sina format with exchange prefix.
        e.g. "600519" → "sh600519", "000001" → "sz000001"
        """
        code_str = str(code).strip()
        if code_str.startswith("sh") or code_str.startswith("sz") or code_str.startswith("bj"):
            return code_str
        if code_str.startswith("6") or code_str.startswith("9"):
            return f"sh{code_str}"
        elif code_str.startswith("0") or code_str.startswith("3") or code_str.startswith("2"):
            return f"sz{code_str}"
        else:
            return f"sh{code_str}"

    @staticmethod
    def is_trading_time() -> bool:
        """Check if current time is within trading hours."""
        now = datetime.now().time()
        from config import TradingTime

        if TradingTime.MORNING_OPEN <= now <= TradingTime.MORNING_CLOSE:
            return True
        if TradingTime.AFTERNOON_OPEN <= now <= TradingTime.AFTERNOON_CLOSE:
            return True
        return False

    @staticmethod
    def is_market_open_today() -> bool:
        """Check if today is a trading day (Sina calendar)."""
        import akshare as ak

        df = ak.tool_trade_date_hist_sina()
        if df.empty:
            return False
        today_dt = date.today()
        row = df[df["trade_date"] == today_dt]
        return not row.empty