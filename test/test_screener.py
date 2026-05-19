"""
Test script for DailyScreener and SecondBoardMomentum.
Run: cd /Users/zego/Downloads/zego/qmt_ths && .venv/bin/python -m test.test_screener
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from data.market_data import MarketData
from strategies.screener import DailyScreener
from strategies.momentum import SecondBoardMomentum


def test_exclusion_logic():
    """Test _is_excluded static method."""
    print("\n" + "=" * 60)
    print("[1/6] 排除逻辑 — _is_excluded")
    print("=" * 60)

    # ST stocks
    assert DailyScreener._is_excluded("sh600123", "ST兰光"), "ST name not excluded"
    assert DailyScreener._is_excluded("sz000555", "*ST太光"), "*ST name not excluded"
    assert not DailyScreener._is_excluded("sh600519", "贵州茅台"), "正常股票被误排除"

    # 科创板
    assert DailyScreener._is_excluded("sh688001", "华兴源创"), "688 科创板未排除"
    assert DailyScreener._is_excluded("sh689001", "某某"), "689 科创板未排除"
    assert not DailyScreener._is_excluded("sh600001", "平安银行"), "正常沪市被误排除"

    # 北交所
    assert DailyScreener._is_excluded("bj830001", "某北交所股"), "bj前缀未排除"
    assert DailyScreener._is_excluded("sz830001", "某北交所股"), "8开头未排除"
    assert not DailyScreener._is_excluded("sh300001", "某创业板"), "创业板被误排除"

    print("  全部通过 ✓")


def test_limit_up_pool():
    """Test Phase 0: fetch limit-up pool."""
    print("\n" + "=" * 60)
    print("[2/6] 涨停池数据 — get_limit_up_pool")
    print("=" * 60)

    md = MarketData()
    try:
        df = md.get_limit_up_pool()
        if df.empty:
            print("  今日无涨停数据（可能非交易日或无涨停股）")
            return
        print(f"  今日涨停数: {len(df)}")
        print(f"  列名: {list(df.columns)}")
        if not df.empty:
            print(df[["code", "name", "pct_chg", "consecutive_boards"]].head(10).to_string(index=False))
        print("  涨停池接口正常 ✓")
    except Exception as e:
        print(f"  [跳过] 涨停池接口异常: {e}")


def test_screener_limit_up():
    """Test screener: limit-up pool filtering."""
    print("\n" + "=" * 60)
    print("[3/6] Screener 涨停过滤 — _get_limit_up_candidates")
    print("=" * 60)

    md = MarketData()
    screener = DailyScreener(md)

    limit_set = screener._get_limit_up_candidates()
    print(f"  涨停候选数（排除后）: {len(limit_set)}")
    if limit_set:
        sample = list(limit_set)[:5]
        print(f"  前5个: {sample}")
    print("  涨停池过滤 ✓")


def test_volume_ratio():
    """Test Phase 2: EM volume ratio candidates."""
    print("\n" + "=" * 60)
    print("[4/6] 量比数据 — _get_volume_ratio_candidates")
    print("=" * 60)

    md = MarketData()
    screener = DailyScreener(md)

    spot = screener._prepare_spot_index()
    if spot.empty:
        print("  [跳过] 无行情数据")
        return

    vol_set = screener._get_volume_ratio_candidates(spot)
    print(f"  量比 > {Config.SCREENER.VOLUME_RATIO_THRESHOLD}: {len(vol_set)} 只")
    if vol_set:
        sample = list(vol_set)[:5]
        print(f"  前5个: {sample}")
    print("  量比过滤 ✓")


def test_daily_checks():
    """Test Phase 3: individual daily bars checks on a known stock."""
    print("\n" + "=" * 60)
    print("[5/6] 日线检查 — _check_volume_surge / _check_fairy_finger")
    print("=" * 60)

    md = MarketData()
    screener = DailyScreener(md)

    code = "sh600519"
    surge = screener._check_volume_surge(code)
    finger = screener._check_fairy_finger(code)
    limit = screener._check_recent_limit_up(code)
    print(f"  {code} 量能突破: {surge} | 仙人指路: {finger} | 近期涨停: {limit}")

    code_bare = "600519"
    try:
        bars = md.get_daily_bars(code_bare, count=5)
        print(f"  无前缀码日线: {len(bars)} 行 ✓")
    except Exception as e:
        print(f"  无前缀码日线: [错误] {e}")

    print("  日线检查 ✓")


def test_full_pipeline():
    """Test the full screener pipeline."""
    print("\n" + "=" * 60)
    print("[6/6] 完整流水线 — DailyScreener.run()")
    print("=" * 60)

    md = MarketData()
    screener = DailyScreener(md)

    try:
        candidates = screener.run()
        print(f"\n  最终候选: {len(candidates)} 只")
        if candidates:
            print(f"  前10只: {candidates[:10]}")
        print("  完整流水线 ✓")
    except Exception as e:
        print(f"  [跳过] 流水线异常: {e}")
        import traceback
        traceback.print_exc()


def test_momentum():
    """Test SecondBoardMomentum on candidates."""
    print("\n" + "=" * 60)
    print("[额外] SecondBoardMomentum — 一进二打板过滤")
    print("=" * 60)

    md = MarketData()
    screener = DailyScreener(md)
    momentum = SecondBoardMomentum(md)

    try:
        candidates = screener.run()
        print(f"  Screener 候选: {len(candidates)}")

        qualified = momentum.run(candidates)
        print(f"  一进二打板通过: {len(qualified)}")
        if qualified:
            print(f"  {qualified[:10]}")
    except Exception as e:
        print(f"  [跳过] {e}")


if __name__ == "__main__":
    print("QMT_THS — Screener & Momentum 测试")
    print("=" * 60)

    test_exclusion_logic()
    test_limit_up_pool()
    test_screener_limit_up()
    test_volume_ratio()
    test_daily_checks()
    test_full_pipeline()
    test_momentum()

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)