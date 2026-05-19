"""
Portfolio & Position Management.
Tracks holdings, cost basis, P&L, and per-position state machines.
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Dict, List, Optional
import json
import os

from config import SystemConfig


# ------------------------------------------------------------------
# Data Models
# ------------------------------------------------------------------
@dataclass
class PositionState:
    """
    Per-position state machine for sell logic.
    Each open position carries one of these.
    """
    code: str
    entry_price: float
    entry_time: datetime
    quantity: int
    remaining_quantity: int  # after partial take-profit
    vwap_at_entry: float
    buy_reason: str  # "vwap_support", "momentum", etc.

    # State flags
    take_profit_1_done: bool = False
    take_profit_2_done: bool = False
    resistance_counter: int = 0
    divergence_start_time: Optional[datetime] = None
    cooling_until: Optional[datetime] = None

    # P&L tracking
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "PositionState":
        d["entry_time"] = datetime.fromisoformat(d["entry_time"])
        if d.get("divergence_start_time"):
            d["divergence_start_time"] = datetime.fromisoformat(d["divergence_start_time"])
        if d.get("cooling_until"):
            d["cooling_until"] = datetime.fromisoformat(d["cooling_until"])
        return cls(**d)


@dataclass
class AccountSnapshot:
    """Daily account snapshot for risk control."""
    date: date
    total_assets: float
    cash: float
    positions_value: float
    consecutive_loss_days: int = 0


class Portfolio:
    """
    Manages positions, account balance, and persistence.
    """

    def __init__(self, filepath: str = SystemConfig.POSITION_FILE):
        self.filepath = filepath
        self.positions: Dict[str, PositionState] = {}  # code → PositionState
        self.cash: float = 1_000_000.0  # initial capital
        self.account_history: List[AccountSnapshot] = []
        self._load()

    # ------------------------------------------------------------------
    # Position CRUD
    # ------------------------------------------------------------------
    def open_position(
        self,
        code: str,
        price: float,
        quantity: int,
        vwap: float,
        reason: str,
    ) -> PositionState:
        """Record a new buy."""
        state = PositionState(
            code=code,
            entry_price=price,
            entry_time=datetime.now(),
            quantity=quantity,
            remaining_quantity=quantity,
            vwap_at_entry=vwap,
            buy_reason=reason,
        )
        self.positions[code] = state
        self.cash -= price * quantity
        self._save()
        return state

    def close_position(self, code: str, exit_price: float) -> Optional[PositionState]:
        """Fully close a position."""
        pos = self.positions.pop(code, None)
        if pos is None:
            return None
        sell_qty = pos.remaining_quantity
        pnl = (exit_price - pos.entry_price) * sell_qty
        pos.realized_pnl += pnl
        pos.remaining_quantity = 0
        self.cash += exit_price * sell_qty
        self._save()
        return pos

    def partial_close(self, code: str, exit_price: float, ratio: float) -> float:
        """Sell a fraction of a position. Returns realized PnL."""
        pos = self.positions.get(code)
        if pos is None:
            return 0.0
        sell_qty = int(pos.remaining_quantity * ratio)
        pnl = (exit_price - pos.entry_price) * sell_qty
        pos.realized_pnl += pnl
        pos.remaining_quantity -= sell_qty
        self.cash += exit_price * sell_qty
        self._save()
        return pnl

    def get_position(self, code: str) -> Optional[PositionState]:
        return self.positions.get(code)

    def has_position(self, code: str) -> bool:
        return code in self.positions

    def total_positions_value(self, current_prices: Dict[str, float]) -> float:
        """Mark-to-market all positions."""
        total = 0.0
        for code, pos in self.positions.items():
            price = current_prices.get(code, pos.entry_price)
            total += price * pos.remaining_quantity
        return total

    def total_assets(self, current_prices: Dict[str, float]) -> float:
        return self.cash + self.total_positions_value(current_prices)

    # ------------------------------------------------------------------
    # Account History & Risk
    # ------------------------------------------------------------------
    def snapshot(self, current_prices: Dict[str, float]) -> AccountSnapshot:
        """Record end-of-day account snapshot."""
        snap = AccountSnapshot(
            date=date.today(),
            total_assets=self.total_assets(current_prices),
            cash=self.cash,
            positions_value=self.total_positions_value(current_prices),
        )
        if self.account_history:
            prev = self.account_history[-1]
            if snap.total_assets < prev.total_assets:
                snap.consecutive_loss_days = prev.consecutive_loss_days + 1
            else:
                snap.consecutive_loss_days = 0
        self.account_history.append(snap)
        self._save()
        return snap

    def get_consecutive_loss_days(self) -> int:
        if not self.account_history:
            return 0
        return self.account_history[-1].consecutive_loss_days

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _save(self):
        data = {
            "cash": self.cash,
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "account_history": [asdict(s) for s in self.account_history],
        }
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _load(self):
        if not os.path.exists(self.filepath):
            return
        with open(self.filepath) as f:
            data = json.load(f)
        self.cash = data.get("cash", self.cash)
        self.positions = {
            k: PositionState.from_dict(v)
            for k, v in data.get("positions", {}).items()
        }
        self.account_history = [
            AccountSnapshot(**s) for s in data.get("account_history", [])
        ]