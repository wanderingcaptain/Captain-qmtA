"""
Intraday Engine — 盘中实时监控与执行引擎。

变更记录：
  v1.1  - 适配新的 Signal 对象（替代原字符串信号）
        - 集成 Notifier 进行推送
        - 替换 print 为 logger
        - 增加主循环的异常防护（使用 Exception 包裹单次 tick，避免系统崩溃）
"""

import time
from datetime import datetime
from typing import List, Optional

from config import Config
from data.market_data import MarketData
from data.portfolio import Portfolio
from strategies.base import SignalType, Signal
from strategies.buy_logic import BuySignal
from strategies.sell_logic import SellSignal
from risk.account_risk import AccountRiskController
from risk.market_risk import MarketRiskController
from utils.notifier import Notifier
from utils.market_utils import calc_position_size
from utils.logger import get_logger

logger = get_logger("core.intraday")


class IntradayEngine:
    """
    盘中实时交易引擎。
    循环流程：风控熔断检测 → 遍历持仓卖出信号 → 账户风控检测 → 遍历自选股买入信号。
    """

    def __init__(self, market_data: MarketData, portfolio: Portfolio):
        self.md = market_data
        self.portfolio = portfolio

        self.notifier = Notifier()

        self.buy = BuySignal(market_data)
        self.sell = SellSignal(market_data)
        self.account_risk = AccountRiskController(portfolio)
        self.market_risk = MarketRiskController(market_data, self.notifier)

        self.watchlist: List[str] = []
        self.is_running: bool = False

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def load_watchlist(self, codes: List[str]):
        """加载夜间筛选出的监控池。"""
        self.watchlist = codes
        logger.info(f"成功加载监控池，共 {len(codes)} 只股票")

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def start(self):
        """启动盘中监控循环。"""
        if not self.watchlist:
            logger.error("监控池为空，引擎终止启动")
            return

        if not self.md.is_trading_time():
            logger.error("当前非交易时间，引擎终止启动")
            return

        self.is_running = True
        logger.info("=========================================")
        logger.info("  盘中引擎启动，开始实时监控")
        logger.info("=========================================")

        while self.is_running:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"Tick 循环发生未捕获异常: {e}", exc_info=True)

            time.sleep(Config.SYSTEM.DATA_FETCH_INTERVAL_SECONDS)

    def stop(self):
        """平滑停止引擎。"""
        self.is_running = False
        logger.info("盘中引擎已接收停止指令")

    # ------------------------------------------------------------------
    # 单次 Tick 逻辑
    # ------------------------------------------------------------------
    def _tick(self):
        """单次监控循环。"""
        now = datetime.now()
        logger.debug(f"--- Tick: {now.strftime('%H:%M:%S')} ---")

        # --- Phase 0: 市场风控（熔断检测） ---
        cb_status = self.market_risk.check_circuit_breaker()
        if cb_status == "full_liquidation":
            logger.critical("触发开盘熔断，执行一键清仓！")
            self._liquidate_all("circuit_breaker")
            return

        # --- Phase 1: 持仓卖出信号评估 ---
        for code, pos in list(self.portfolio.positions.items()):
            signal: Signal = self.sell.evaluate_all(pos)

            if signal.type == SignalType.SELL_FULL:
                logger.info(f"[卖出] {code} 全仓平仓，原因：{signal.reason}")
                current_price = self.md.get_price(code)
                pnl = self.portfolio.close_position(code, current_price)
                if pnl:
                    self.notifier.send_alert(
                        "全仓平仓",
                        f"{code} 触发 {signal.reason}，成交价 {current_price:.2f}",
                        "WARNING"
                    )

            elif signal.type == SignalType.SELL_PARTIAL:
                ratio = signal.sell_ratio
                logger.info(f"[卖出] {code} 部分平仓 {ratio:.0%}，原因：{signal.reason}")
                current_price = self.md.get_price(code)
                self.portfolio.partial_close(code, current_price, ratio)
                self.notifier.send_alert(
                    "部分平仓",
                    f"{code} 触发 {signal.reason} ({ratio:.0%})，成交价 {current_price:.2f}",
                    "INFO"
                )

        # --- Phase 2: 账户风控检测 ---
        if self.account_risk.should_liquidate_all():
            logger.critical("触发账户风控限制，执行一键清仓！")
            self.notifier.alert_consecutive_loss(self.account_risk.get_consecutive_loss_days())
            self._liquidate_all("consecutive_loss")
            return

        if self.account_risk.should_suspend_buying():
            logger.debug("账户处于买入暂停期，跳过买入评估")
            return

        # --- Phase 3: 自选股买入信号评估 ---
        cap = min(
            self.account_risk.get_position_cap(),
            self.market_risk.get_position_cap(),
        )
        if cap <= 0:
            logger.debug("当前仓位上限为 0，跳过买入评估")
            return

        open_slots = max(0, Config.BUY.MAX_OPEN_POSITIONS - len(self.portfolio.positions))
        if open_slots <= 0:
            return

        for code in self.watchlist:
            if open_slots <= 0:
                break
            if self.portfolio.has_position(code):
                continue

            if self.buy.evaluate(code):
                price = self.md.get_price(code)
                if price <= 0:
                    continue
                vwap = self.md.get_vwap(code)
                if vwap <= 0:
                    continue

                # 使用公共帮助函数计算股数
                quantity = calc_position_size(
                    cash=self.portfolio.cash,
                    price=price,
                    cap=cap,
                    max_stocks=Config.BUY.MAX_OPEN_POSITIONS
                )
                if quantity > 0:
                    self.portfolio.open_position(code, price, quantity, vwap, "vwap_support")
                    logger.info(f"[买入] {code} 数量={quantity} 价格={price:.2f}")
                    self.notifier.send_alert(
                        "开仓买入",
                        f"{code} 触发支撑买入，数量 {quantity}，价格 {price:.2f}",
                        "INFO"
                    )
                    open_slots -= 1

        # --- Phase 4: 盘后结算快照 ---
        if now.time() >= Config.SELL.BREAKDOWN_CHECK_TIME:
            current_prices = {
                code: self.md.get_price(code)
                for code in list(self.portfolio.positions.keys())
            }
            snap = self.portfolio.snapshot(current_prices)
            logger.info(f"盘后快照生成：总资产 {snap.total_assets:.2f}，连亏天数 {snap.consecutive_loss_days}")
            self.account_risk.reset_after_recovery()

    def _liquidate_all(self, reason: str):
        """紧急一键清仓。"""
        for code, pos in list(self.portfolio.positions.items()):
            price = self.md.get_price(code)
            self.portfolio.close_position(code, price)
            logger.critical(f"[紧急清仓] {code} 数量={pos.remaining_quantity} 价格={price:.2f} (原因: {reason})")