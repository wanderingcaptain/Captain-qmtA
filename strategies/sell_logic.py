"""
卖出逻辑 — 盘中卖出/退出信号检测。
包含止损状态机、止盈、遇阻、量价背离、日线破位五大信号。

变更记录：
  v1.1  - 返回值从 str 改为 Signal 对象（见 strategies/base.py）
        - 修复 check_resistance()：touched_band 应检查 high >= vwap_upper 而非 vwap_lower
        - 修复 check_take_profit()：if tp_ratio → if tp_ratio is not None
        - 优化：evaluate_all() 只获取一次当前价格，传递给各子检查方法
"""

from datetime import datetime
from typing import Optional

import pandas as pd

from config import Config
from data.market_data import MarketData
from data.portfolio import PositionState
from strategies.base import Signal
from utils.logger import get_logger

logger = get_logger("strategies.sell")


class SellSignal:
    """
    评估每只持仓的卖出信号。
    通过 PositionState 维护每只持仓的状态机。
    """

    def __init__(self, market_data: MarketData):
        self.md = market_data

    # ------------------------------------------------------------------
    # 1. 止损：price < VWAP * (1 - threshold)
    # ------------------------------------------------------------------
    def check_stop_loss(self, pos: PositionState, current_price: float) -> bool:
        """动态止损：现价低于入场 VWAP 的 (1 - 止损比) 时触发。"""
        if current_price <= 0:
            return False
        threshold = pos.vwap_at_entry * (1 - Config.SELL.STOP_LOSS_VWAP_PCT)
        triggered = current_price < threshold
        if triggered:
            logger.debug(
                f"[止损] {pos.code} 现价={current_price:.2f} < 阈值={threshold:.2f}"
            )
        return triggered

    # ------------------------------------------------------------------
    # 2. 止盈状态机：+3% 卖50%，+5% 卖剩余50%
    # ------------------------------------------------------------------
    def check_take_profit(
        self, pos: PositionState, current_price: float
    ) -> Optional[float]:
        """
        返回卖出比例（0.0–1.0），无触发则返回 None。
        修复：使用 `is not None` 判断，避免 0.0 被误判为无信号。
        """
        gain_pct = (current_price - pos.entry_price) / pos.entry_price

        # Level 2：+5% → 卖剩余 50%（优先检查，避免只触发 level1）
        if gain_pct >= Config.SELL.TAKE_PROFIT_2_PCT and not pos.take_profit_2_done:
            pos.take_profit_2_done = True
            logger.debug(
                f"[止盈2] {pos.code} 涨幅={gain_pct:.1%} 触发，卖出 "
                f"{Config.SELL.TAKE_PROFIT_2_RATIO:.0%}"
            )
            return Config.SELL.TAKE_PROFIT_2_RATIO

        # Level 1：+3% → 卖 50%
        if gain_pct >= Config.SELL.TAKE_PROFIT_1_PCT and not pos.take_profit_1_done:
            pos.take_profit_1_done = True
            logger.debug(
                f"[止盈1] {pos.code} 涨幅={gain_pct:.1%} 触发，卖出 "
                f"{Config.SELL.TAKE_PROFIT_1_RATIO:.0%}"
            )
            return Config.SELL.TAKE_PROFIT_1_RATIO

        return None

    # ------------------------------------------------------------------
    # 3. 遇阻（VWAP 压力）
    # ------------------------------------------------------------------
    def check_resistance(self, pos: PositionState, current_price: float) -> bool:
        """
        若高点触及 VWAP 上方 ±band 后，连续 N 根收盘低于 VWAP → 计数器
        到达上限时触发卖出。

        修复（Bug #2）：touched_band 检查的是 high >= vwap_upper（上界），
        而非原来的 vwap_lower（下界，恒为 True）。
        """
        vwap = self.md.get_vwap(pos.code)
        if vwap <= 0:
            return False

        band = Config.SELL.RESISTANCE_VWAP_BAND_PCT
        vwap_lower = vwap * (1 - band)
        vwap_upper = vwap * (1 + band)

        bars = self.md.get_minute_bars(pos.code)
        if bars is None or len(bars) < 2:
            return False

        last_two = bars.tail(2)

        # 修复：高点需触及 VWAP 上方压力区（>= vwap_upper）才算遇阻
        touched_band = last_two["high"].max() >= vwap_upper
        if not touched_band:
            return False

        # 连续 N 根收盘低于 VWAP
        closes_below = (last_two["close"] < vwap_lower).sum()
        if closes_below >= Config.SELL.RESISTANCE_CONSECUTIVE_BARS:
            pos.resistance_counter += 1
            logger.debug(
                f"[遇阻] {pos.code} 计数器 {pos.resistance_counter}/"
                f"{Config.SELL.RESISTANCE_COUNTER_LIMIT}"
            )

        return pos.resistance_counter >= Config.SELL.RESISTANCE_COUNTER_LIMIT

    # ------------------------------------------------------------------
    # 4. 量价背离
    # ------------------------------------------------------------------
    def check_divergence(self, pos: PositionState, current_price: float) -> bool:
        """
        量比 > 阈值 且 涨幅在 [1%, 2.5%] 持续 > 5 分钟 → 背离卖出。
        """
        vol_ratio = self.md.get_volume_ratio(pos.code)
        if vol_ratio <= Config.SELL.DIVERGENCE_VOLUME_RATIO_THRESHOLD:
            pos.divergence_start_time = None
            return False

        gain_pct = (current_price - pos.entry_price) / pos.entry_price
        in_range = (
            Config.SELL.DIVERGENCE_GAIN_MIN_PCT
            <= gain_pct
            <= Config.SELL.DIVERGENCE_GAIN_MAX_PCT
        )
        if not in_range:
            pos.divergence_start_time = None
            return False

        if pos.divergence_start_time is None:
            pos.divergence_start_time = datetime.now()
            return False

        elapsed = (datetime.now() - pos.divergence_start_time).total_seconds()
        if elapsed >= Config.SELL.DIVERGENCE_DURATION_MINUTES * 60:
            logger.debug(
                f"[背离] {pos.code} 量比={vol_ratio:.1f} 涨幅={gain_pct:.1%} "
                f"持续 {elapsed/60:.1f}min"
            )
            return True
        return False

    # ------------------------------------------------------------------
    # 5. 日线破位（昨日台阶理论）
    # ------------------------------------------------------------------
    def check_daily_breakdown(self, code: str, current_price: float) -> bool:
        """14:50 后现价 < min(昨收, 前日收) → 破位卖出。"""
        now = datetime.now().time()
        if now < Config.SELL.BREAKDOWN_CHECK_TIME:
            return False

        bars = self.md.get_daily_bars(code, count=5)
        if bars is None or len(bars) < 3:
            return False

        yesterday_close = bars.iloc[-2]["close"]
        day_before_close = bars.iloc[-3]["close"]
        floor = min(yesterday_close, day_before_close)

        if current_price < floor:
            logger.debug(
                f"[破位] {code} 现价={current_price:.2f} < 台阶={floor:.2f}"
            )
            return True
        return False

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def evaluate_all(self, pos: PositionState) -> Signal:
        """
        运行所有卖出检查，按优先级返回第一个触发的信号。
        优先级：止损 > 止盈 > 遇阻 > 背离 > 破位

        优化：只调用一次 get_price()，传递给各检查方法。
        返回 Signal 对象（替代原来的字符串）。
        """
        current_price = self.md.get_price(pos.code)
        if current_price <= 0:
            return Signal.hold()

        # 1. 止损
        if self.check_stop_loss(pos, current_price):
            return Signal.sell_full("stop_loss")

        # 2. 止盈
        tp_ratio = self.check_take_profit(pos, current_price)
        if tp_ratio is not None:  # 修复 Bug #3：不再用 if tp_ratio
            return Signal.sell_partial("take_profit", tp_ratio)

        # 3. 遇阻
        if self.check_resistance(pos, current_price):
            return Signal.sell_full("resistance")

        # 4. 背离
        if self.check_divergence(pos, current_price):
            return Signal.sell_full("divergence")

        # 5. 破位
        if self.check_daily_breakdown(pos.code, current_price):
            return Signal.sell_full("daily_breakdown")

        return Signal.hold()