"""
Test script for IntradayEngine, BuySignal, SellSignal, and Portfolio.
Run: cd /Users/zego/Downloads/zego/qmt_ths && .venv/bin/python -m test.test_intraday
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from config import Config
from data.market_data import MarketData
from data.portfolio import Portfolio, PositionState
from strategies.buy_logic import BuySignal
from strategies.sell_logic import SellSignal
from core.intraday_engine import IntradayEngine


def test_portfolio_open_close():
    """Test position open/close and cash tracking."""
    print("\n" + "=" * 60)
    print("[1/7] Portfolio — 开仓/平仓/现金")
    print("=" * 60)

    pf = Portfolio(filepath="/tmp/test_portfolio.json")
    pf.cash = 1_000_000.0

    pos = pf.open_position("600519", 1500.0, 200, 1495.0, "vwap_support")
    assert pos.code == "600519"
    assert pos.quantity == 200
    assert pf.cash == 1_000_000 - 1500 * 200  # 700,000
    print(f"  开仓后现金: {pf.cash:.2f}")

    pos2 = pf.close_position("600519", 1550.0)
    assert pos2 is not None
    assert pos2.realized_pnl > 0
    print(f"  平仓盈亏: {pos2.realized_pnl:.2f}")
    print(f"  平仓后现金: {pf.cash:.2f}")
    assert "600519" not in pf.positions

    print("  Portfolio 开仓/平仓 ✓")


def test_portfolio_partial_close():
    """Test partial take-profit."""
    print("\n" + "=" * 60)
    print("[2/7] Portfolio — 分批卖出")
    print("=" * 60)

    pf = Portfolio(filepath="/tmp/test_portfolio.json")
    pf.cash = 1_000_000.0

    pos = pf.open_position("000001", 10.0, 1000, 9.95, "vwap_support")
    assert pf.positions["000001"].remaining_quantity == 1000

    pnl = pf.partial_close("000001", 10.5, 0.5)
    assert pnl > 0
    assert pf.positions["000001"].remaining_quantity == 500
    print(f"  分批卖出盈亏: {pnl:.2f}, 剩余: {pf.positions['000001'].remaining_quantity}")

    pf.close_position("000001", 10.8)
    assert "000001" not in pf.positions
    print("  分批卖出 ✓")


def test_portfolio_snapshot():
    """Test EOD snapshot and consecutive loss tracking."""
    print("\n" + "=" * 60)
    print("[3/7] Portfolio — 快照/连续亏损")
    print("=" * 60)

    pf = Portfolio(filepath="/tmp/test_portfolio.json")
    pf.cash = 1_000_000.0

    # Snapshot without positions
    snap1 = pf.snapshot({})
    assert snap1.total_assets == 1_000_000.0
    print(f"  快照1 总资产: {snap1.total_assets}")

    # Simulate a loss day
    pf.cash = 900_000.0
    snap2 = pf.snapshot({})
    assert snap2.consecutive_loss_days == 1
    print(f"  快照2 连续亏损: {snap2.consecutive_loss_days}")

    # Another loss
    pf.cash = 800_000.0
    snap3 = pf.snapshot({})
    assert snap3.consecutive_loss_days == 2
    print(f"  快照3 连续亏损: {snap3.consecutive_loss_days}")

    # Recovery
    pf.cash = 900_000.0
    snap4 = pf.snapshot({})
    assert snap4.consecutive_loss_days == 0
    print(f"  快照4 恢复后亏损天数: {snap4.consecutive_loss_days}")

    print("  快照/亏损跟踪 ✓")


def test_buy_time_window():
    """Test buy time window filter."""
    print("\n" + "=" * 60)
    print("[4/7] BuySignal — 时间窗口")
    print("=" * 60)

    assert not BuySignal._check_time_window()  # not in trading hours (after market)
    print("  盘后买入窗口: False ✓")


def test_buy_macro_filter():
    """Test buy macro sentiment filter relies on live data."""
    print("\n" + "=" * 60)
    print("[5/7] BuySignal — 大盘情绪")
    print("=" * 60)

    md = MarketData()
    buy = BuySignal(md)
    try:
        result = buy._check_macro_sentiment()
        print(f"  大盘情绪: {'通过' if result else '未通过 (上涨家数 < 3000)'}")
        print("  大盘情绪过滤器验证 ✓")
    except Exception as e:
        print(f"  [跳过] 大盘情绪异常: {e}")


def test_sell_stop_loss():
    """Test stop-loss detection."""
    print("\n" + "=" * 60)
    print("[6/7] SellSignal — 止损/止盈")
    print("=" * 60)

    md = MarketData()
    sell = SellSignal(md)

    # Create a position with entry VWAP at 100
    pos = PositionState(
        code="600519",
        entry_price=100.0,
        entry_time=datetime.now(),
        quantity=1000,
        remaining_quantity=1000,
        vwap_at_entry=100.0,
        buy_reason="vwap_support",
    )

    # Stop-loss: 100 * (1 - 0.01) = 99, current ~1323 → no
    sl = sell.check_stop_loss(pos)
    print(f"  止损 (现价~1323, 阈值99): {sl}")

    # Expect False")
    assert not sl, "当前股价远高于止损线，不应触发止损"

    # Take-profit check: gain ~(1323-100)/100 = 1223% → take-profit level 2
    tp_ratio = sell.check_take_profit(pos)
    print(f"  止盈: {tp_ratio}")
    if tp_ratio:
        print(f"  止盈比例: {tp_ratio}")

    print("  止损/止盈逻辑 ✓")


def test_intraday_engine_init():
    """Test engine initialization and watchlist loading."""
    print("\n" + "=" * 60)
    print("[7/7] IntradayEngine — 初始化")
    print("=" * 60)

    md = MarketData()
    pf = Portfolio(filepath="/tmp/test_portfolio.json")
    engine = IntradayEngine(md, pf)

    assert engine.watchlist == []
    assert not engine.is_running

    engine.load_watchlist(["600519", "000001", "300750"])
    assert len(engine.watchlist) == 3

    # Test start rejects outside trading hours
    engine.start()  # Should print "Outside trading hours. Aborting."
    assert not engine.is_running

    print("  IntradayEngine 初始化 ✓")


if __name__ == "__main__":
    print("QMT_THS — Intraday/Buy/Sell/Portfolio 测试")
    print("=" * 60)

    test_portfolio_open_close()
    test_portfolio_partial_close()
    test_portfolio_snapshot()
    test_buy_time_window()
    test_buy_macro_filter()
    test_sell_stop_loss()
    test_intraday_engine_init()

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)