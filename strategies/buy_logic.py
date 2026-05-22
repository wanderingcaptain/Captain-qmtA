"""
买入逻辑 — 盘中买入信号检测。
三层过滤：宏观情绪 → 时间窗口 → VWAP 微观形态。

变更记录：
  v1.1  - 修复 Bug #4：_check_rapid_rally 触发冷却后，_check_vwap_support 应返回 False
          原代码在设置冷却后仍然 return True，导致急拉信号被执行。
        - _cooling_map 改名含义更清晰（存储冷却开始时间）
        - 使用 get_logger 替代 print
"""

from datetime import datetime, time
from typing import Optional

import pandas as pd

from config import Config
from data.market_data import MarketData
from utils.logger import get_logger

logger = get_logger("strategies.buy")


class BuySignal:
    """
    评估自选股的买入信号。
    三个过滤层全部通过才触发买入。
    """

    def __init__(self, market_data: MarketData):
        self.md = market_data
        # code → 冷却开始时间（datetime）
        self._cooling_start: dict = {}

    # ------------------------------------------------------------------
    # Layer 1: 宏观情绪
    # ------------------------------------------------------------------
    def _check_macro_sentiment(self) -> bool:
        """上涨家数 >= 阈值才允许买入。"""
        advancing, declining, flat = self.md.get_market_advancing_declining()
        ok = advancing >= Config.MACRO.ADVANCING_STOCKS_THRESHOLD
        if not ok:
            logger.debug(
                f"[宏观过滤] 上涨家数 {advancing} < {Config.MACRO.ADVANCING_STOCKS_THRESHOLD}"
            )
        return ok

    # ------------------------------------------------------------------
    # Layer 2: 时间窗口
    # ------------------------------------------------------------------
    @staticmethod
    def _check_time_window() -> bool:
        """
        允许买入的时间窗口：
          09:30–10:40  OR  14:40–14:55
        """
        now = datetime.now().time()
        w1s = Config.TRADING_TIME.BUY_WINDOW_1_START
        w1e = Config.TRADING_TIME.BUY_WINDOW_1_END
        w2s = Config.TRADING_TIME.BUY_WINDOW_2_START
        w2e = Config.TRADING_TIME.BUY_WINDOW_2_END
        return (w1s <= now <= w1e) or (w2s <= now <= w2e)

    # ------------------------------------------------------------------
    # Layer 3: VWAP 支撑形态（微观）
    # ------------------------------------------------------------------
    def _check_vwap_support(self, code: str) -> bool:
        """
        VWAP 支撑形态：
        1. T 分钟低点在 VWAP ±0.5% 区间内
        2. 后续 N 分钟收盘均站稳 VWAP
        3. T 分钟成交量 < 前 5 分钟均量的 50%（缩量）
        4. 不在急拉冷却期内

        修复 Bug #4：先检测急拉并更新冷却，然后返回 False（而非原来
        在设置冷却后仍 return True）。
        """
        if self._in_cooling(code):
            return False

        bars = self.md.get_minute_bars(code)
        if bars is None or len(bars) < 10:
            return False

        vwap = self.md.get_vwap(code)
        if vwap <= 0:
            return False

        vwap_lower = vwap * (1 - Config.BUY.VWAP_BAND_PERCENT)
        vwap_upper = vwap * (1 + Config.BUY.VWAP_BAND_PERCENT)
        conf = Config.BUY.VWAP_CONFIRM_MINUTES

        for i in range(len(bars) - 1, max(len(bars) - 20, 0), -1):
            t_bar = bars.iloc[i]
            low_t = t_bar["low"]

            # 条件 1：低点触 VWAP 带
            if not (vwap_lower <= low_t <= vwap_upper):
                continue

            # 条件 2：后续 N 分钟收盘站稳 VWAP
            if i + conf >= len(bars):
                continue
            holds = all(
                bars.iloc[j]["close"] >= vwap
                for j in range(i + 1, i + conf + 1)
            )
            if not holds:
                continue

            # 条件 3：缩量
            vol_t = t_bar["volume"]
            avg_vol = bars.iloc[
                max(0, i - Config.BUY.VOLUME_LOOKBACK_MINUTES): i
            ]["volume"].mean()
            if avg_vol > 0 and vol_t / avg_vol >= Config.BUY.VOLUME_SHRINK_RATIO:
                continue

            # 条件 4（修复）：检测急拉；如果触发冷却则本次不买
            if self._detect_rapid_rally(code, bars, i):
                logger.info(f"[急拉冷却] {code} 触发冷却，跳过买入")
                return False  # 修复：设置冷却后不再继续，直接返回 False

            logger.info(
                f"[VWAP支撑] {code} 触发 @ bar[{i}] "
                f"low={low_t:.2f} vwap={vwap:.2f}"
            )
            return True

        return False

    # ------------------------------------------------------------------
    # 急拉冷却（急拉不买）
    # ------------------------------------------------------------------
    def _detect_rapid_rally(self, code: str, bars: pd.DataFrame, current_idx: int) -> bool:
        """
        检测是否发生急拉（3分钟涨 >3% 且量 >3× 早盘均量）。
        若是，设置冷却期并返回 True。
        """
        lb = Config.BUY.RAPID_RALLY_LOOKBACK_MINUTES
        if current_idx < lb:
            return False

        near = bars.iloc[current_idx - lb: current_idx + 1]
        open_price = near.iloc[0]["open"]
        if open_price <= 0:
            return False

        price_change = (near.iloc[-1]["close"] - open_price) / open_price
        if price_change < Config.BUY.RAPID_RALLY_PRICE_PCT:
            return False

        # 量能检查
        baseline_n = Config.BUY.EARLY_SESSION_BASELINE_MINUTES
        if len(bars) < baseline_n:
            return False
        early_avg_vol = bars.head(baseline_n)["volume"].mean()
        if early_avg_vol <= 0:
            return False

        surge_vol = near["volume"].mean()
        if surge_vol > early_avg_vol * Config.BUY.RAPID_RALLY_VOLUME_MULTIPLE:
            self._cooling_start[code] = datetime.now()
            logger.debug(
                f"[急拉检测] {code} 涨幅={price_change:.1%} "
                f"量={surge_vol:.0f} vs 基准={early_avg_vol:.0f}"
            )
            return True
        return False

    def _in_cooling(self, code: str) -> bool:
        """检查股票是否仍在急拉冷却期内。"""
        start = self._cooling_start.get(code)
        if start is None:
            return False
        elapsed = (datetime.now() - start).total_seconds()
        if elapsed > Config.BUY.COOLING_PERIOD_MINUTES * 60:
            del self._cooling_start[code]
            return False
        return True

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def evaluate(self, code: str) -> bool:
        """
        完整买入信号流水线：宏观 → 时间 → 微观。
        全部通过返回 True。
        """
        if not self._check_macro_sentiment():
            return False
        if not self._check_time_window():
            return False
        return self._check_vwap_support(code)