"""
Intraday Engine — Real-time Monitoring & Execution.
Runs during trading hours. Focuses only on the core watchlist.
Handles: minute-level data refresh, buy/sell signal evaluation, risk checks.
"""

import time
from datetime import datetime
from typing import Dict, List, Optional

from config import Config
from data.market_data import MarketData
from data.portfolio import Portfolio
from strategies.buy_logic import BuySignal
from strategies.sell_logic import SellSignal
from risk.account_risk import AccountRiskController
from risk.market_risk import MarketRiskController


class IntradayEngine:
    """
    Real-time intraday trading engine.
    Main loop: refresh data → evaluate sell → evaluate buy → risk check → sleep.
    """

    def __init__(self, market_data: MarketData, portfolio: Portfolio):
        self.md = market_data
        self.portfolio = portfolio

        self.buy = BuySignal(market_data)
        self.sell = SellSignal(market_data)
        self.account_risk = AccountRiskController(portfolio)
        self.market_risk = MarketRiskController(market_data)

        self.watchlist: List[str] = []
        self.is_running: bool = False

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def load_watchlist(self, codes: List[str]):
        """Load the core monitoring pool (from nightly engine output)."""
        self.watchlist = codes
        print(f"[IntradayEngine] Loaded watchlist with {len(codes)} stocks")

    # ------------------------------------------------------------------
    # Main Loop
    # ------------------------------------------------------------------
    def start(self):
        """Start the intraday monitoring loop."""
        if not self.watchlist:
            print("[IntradayEngine] Watchlist is empty. Aborting.")
            return

        if not self.md.is_trading_time():
            print("[IntradayEngine] Outside trading hours. Aborting.")
            return

        self.is_running = True
        print(f"[IntradayEngine] Started at {datetime.now()}")

        while self.is_running:
            try:
                self._tick()
            except Exception as e:
                print(f"[IntradayEngine] Error in tick: {e}")

            time.sleep(Config.SYSTEM.DATA_FETCH_INTERVAL_SECONDS)

    def stop(self):
        """Gracefully stop the engine."""
        self.is_running = False
        print(f"[IntradayEngine] Stopped at {datetime.now()}")

    # ------------------------------------------------------------------
    # Single Tick
    # ------------------------------------------------------------------
    def _tick(self):
        """One iteration of the monitoring loop."""
        now = datetime.now()
        print(f"\n--- Tick at {now} ---")

        # --- Phase 0: Market risk check ---
        cb_status = self.market_risk.check_circuit_breaker()
        if cb_status == "full_liquidation":
            print("[IntradayEngine] CIRCUIT BREAKER: Full liquidation triggered!")
            self._liquidate_all("circuit_breaker")
            return
        elif cb_status == "half_cap":
            cap = self.market_risk.get_position_cap()
            print(f"[IntradayEngine] CIRCUIT BREAKER: Position cap = {cap}")

        # --- Phase 1: Evaluate sell for all open positions ---
        for code, pos in list(self.portfolio.positions.items()):
            current_price = self.md.get_price(code)
            if current_price <= 0:
                continue

            signal = self.sell.evaluate_all(pos)

            if signal == "stop_loss":
                print(f"[SELL] {code}: Stop-loss triggered")
                self.portfolio.close_position(code, current_price)

            elif signal and signal.startswith("take_profit"):
                ratio = float(signal.split(":")[1])
                print(f"[SELL] {code}: Take-profit {ratio*100:.0f}%")
                self.portfolio.partial_close(code, current_price, ratio)

            elif signal == "resistance":
                print(f"[SELL] {code}: Intraday resistance triggered")
                self.portfolio.close_position(code, current_price)

            elif signal == "divergence":
                print(f"[SELL] {code}: Volume-price divergence triggered")
                self.portfolio.close_position(code, current_price)

            elif signal == "daily_breakdown":
                print(f"[SELL] {code}: Daily breakdown (step theory)")
                self.portfolio.close_position(code, current_price)

        # --- Phase 2: Account risk check ---
        if self.account_risk.should_liquidate_all():
            print("[IntradayEngine] Account risk: Forced liquidation!")
            self._liquidate_all("consecutive_loss")
            return

        if self.account_risk.should_suspend_buying():
            print("[IntradayEngine] Account risk: Buying suspended")
            return

        # --- Phase 3: Evaluate buy for watchlist stocks ---
        cap = min(
            self.account_risk.get_position_cap(),
            self.market_risk.get_position_cap(),
        )
        if cap <= 0:
            print("[IntradayEngine] Position cap is zero. Skipping buys.")
            return

        open_slots = max(0, Config.BUY.MAX_OPEN_POSITIONS - len(self.portfolio.positions))
        if open_slots <= 0:
            return

        cash_per_stock = self.portfolio.cash * cap / open_slots
        for code in self.watchlist:
            if self.portfolio.has_position(code):
                continue  # already holding

            if self.buy.evaluate(code):
                price = self.md.get_price(code)
                if price <= 0:
                    continue
                vwap = self.md.get_vwap(code)
                if vwap <= 0:
                    continue

                quantity = int(cash_per_stock / price / 100) * 100  # A-share: 100-share lots
                if quantity > 0:
                    self.portfolio.open_position(code, price, quantity, vwap, "vwap_support")
                    print(f"[BUY] {code}: {quantity} shares @ {price:.2f}")

        # --- Phase 4: End-of-day snapshot ---
        if now.time() >= Config.SELL.BREAKDOWN_CHECK_TIME:
            current_prices = {
                code: self.md.get_price(code) for code in list(self.portfolio.positions.keys())
            }
            snap = self.portfolio.snapshot(current_prices)
            print(f"[IntradayEngine] EOD snapshot: assets={snap.total_assets:.2f}")

    def _liquidate_all(self, reason: str):
        """Emergency liquidation of all positions."""
        for code, pos in list(self.portfolio.positions.items()):
            price = self.md.get_price(code)
            self.portfolio.close_position(code, price)
            print(f"[LIQUIDATE] {code}: {pos.remaining_quantity} shares @ {price:.2f} (reason: {reason})")