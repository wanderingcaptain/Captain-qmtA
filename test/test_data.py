"""
Test script for MarketData data interfaces.
Run: cd /Users/zego/Downloads/zego/qmt_ths && .venv/bin/python -m test.test_data
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.market_data import MarketData


def test_spot_data():
    print("\n" + "=" * 60)
    print("[1/7] 实时行情 — get_stock_list / get_price")
    print("=" * 60)

    md = MarketData()
    codes = md.get_stock_list()
    print(f"  A股总数: {len(codes)}")
    print(f"  前5个: {codes[:5]}")

    # Use correct prefix for Sina format
    price = md.get_price("sh600519")
    ask_bid = md.get_current_ask_bid("sh600519")
    print(f"  sh600519 最新价: {price}")
    print(f"  实时行情: { {k: ask_bid[k] for k in ('price', 'open', 'high', 'low', 'prev_close', 'pct_chg')} }")


def test_market_adv_dec():
    print("\n" + "=" * 60)
    print("[2/7] 涨跌家数 — get_market_advancing_declining")
    print("=" * 60)

    adv, dec, flat = MarketData.get_market_advancing_declining()
    print(f"  上涨: {adv}  下跌: {dec}  平盘: {flat}")


def test_daily_bars():
    print("\n" + "=" * 60)
    print("[3/7] 日线数据 — get_daily_bars")
    print("=" * 60)

    md = MarketData()
    df = md.get_daily_bars("600519", count=5)
    print(f"  列名: {list(df.columns)}")
    print(f"  行数: {len(df)}")
    print(df[["date", "open", "high", "low", "close", "volume"]].to_string(index=False))


def test_limit_up():
    print("\n" + "=" * 60)
    print("[4/7] 涨停日查询 — get_limit_up_prices")
    print("=" * 60)

    md = MarketData()
    df = md.get_limit_up_prices("600519", lookback=60)
    print(f"  近60日涨停次数: {len(df)}")
    if not df.empty:
        print(df.to_string(index=False))


def test_minute_bars():
    print("\n" + "=" * 60)
    print("[5/7] 分钟线 — get_minute_bars / get_vwap")
    print("=" * 60)

    md = MarketData()
    df = md.get_minute_bars("600519")
    print(f"  今日分钟线行数: {len(df)}")
    if not df.empty:
        print(f"  列名: {list(df.columns)}")
        print(df.tail(3).to_string(index=False))
        vwap = md.get_vwap("600519")
        print(f"  当前VWAP: {vwap:.2f}")


def test_market_cap():
    print("\n" + "=" * 60)
    print("[6/7] 个股信息 — get_stock_info / get_market_cap")
    print("=" * 60)

    md = MarketData()
    info = md.get_stock_info("600519")
    print(f"  总市值: {info.get('总市值', 'N/A')}")
    print(f"  流通市值: {info.get('流通市值', 'N/A')}")
    print(f"  行业: {info.get('行业', 'N/A')}")

    cap = md.get_market_cap("000001")
    print(f"  000001 总市值: {cap:.2f}")


def test_market_open():
    print("\n" + "=" * 60)
    print("[7/7] 交易日判断 — is_market_open_today / is_trading_time")
    print("=" * 60)

    is_open = MarketData.is_market_open_today()
    is_time = MarketData.is_trading_time()
    print(f"  今日开盘: {is_open}")
    print(f"  当前交易时间: {is_time}")


if __name__ == "__main__":
    print("QMT_THS — MarketData 接口测试 (Sina Backend)")
    print("=" * 60)

    test_spot_data()
    test_market_adv_dec()
    test_daily_bars()
    test_limit_up()
    test_minute_bars()
    test_market_cap()
    test_market_open()

    print("\n" + "=" * 60)
    print("全部测试完成！")
    print("=" * 60)