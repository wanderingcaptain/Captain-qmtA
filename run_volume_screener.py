"""
量比选股 — 调用东财量比数据，筛选量比 > 2 的股票，保存到 screening_results/。
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.market_data import MarketData

RESULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screening_results")


def main():
    print("=" * 60)
    print("  量比选股 — 东财实时量比筛选")
    print("=" * 60)

    md = MarketData()

    # 1) 获取东财量比（含名称、价格、涨幅）
    t0 = datetime.now()
    print("\n[1/2] 获取全市场量比数据...")
    vol_df = md._get_em_spot_volume_ratios()
    print(f"  获取到 {len(vol_df)} 只股票的量比数据 ({(datetime.now()-t0).total_seconds():.1f}s)")

    # 2) 筛选量比 > 2
    threshold = 2.0
    filtered = vol_df[vol_df["volume_ratio"] > threshold].copy()
    filtered = filtered.sort_values("volume_ratio", ascending=False)

    rows = []
    for _, row in filtered.iterrows():
        rows.append({
            "code": str(row["code"]),
            "name": str(row.get("name", "")),
            "price": float(row.get("price", 0)),
            "pct_chg": float(row.get("pct_chg", 0)),
            "volume_ratio": float(row["volume_ratio"]),
        })

    print(f"\n[2/2] 量比 > {threshold}: {len(rows)} 只")

    # 保存
    os.makedirs(RESULT_DIR, exist_ok=True)
    now = datetime.now()
    filename = now.strftime("%Y-%m-%d_%H%M%S")
    json_path = os.path.join(RESULT_DIR, f"volume_ratio_{filename}.json")
    txt_path = os.path.join(RESULT_DIR, f"volume_ratio_{filename}.txt")

    # JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "time": now.isoformat(),
            "threshold": threshold,
            "total": len(rows),
            "stocks": rows,
        }, f, ensure_ascii=False, indent=2)

    # TXT
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"量比选股 — {now.strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"{'='*60}\n")
        f.write(f"阈值: 量比 > {threshold}\n")
        f.write(f"总数: {len(rows)} 只\n\n")

        f.write(f"{'代码':>8}  {'名称':<8}  {'价格':>8}  {'涨幅%':>8}  {'量比':>8}\n")
        f.write("─" * 50 + "\n")
        for r in rows:
            f.write(f"{r['code']:>8}  {r['name']:<8}  {r['price']:>8.2f}  "
                    f"{r['pct_chg']:>8.2f}  {r['volume_ratio']:>8.1f}\n")

    print(f"\n  保存:")
    print(f"    JSON: {json_path}")
    print(f"    TXT:  {txt_path}")

    # 屏幕输出前20
    print(f"\n{'='*60}")
    print(f"  量比排行 TOP 20")
    print(f"{'='*60}")
    print(f"{'代码':>8}  {'名称':<8}  {'价格':>8}  {'涨幅%':>8}  {'量比':>8}")
    print("─" * 50)
    for r in rows[:20]:
        print(f"{r['code']:>8}  {r['name']:<8}  {r['price']:>8.2f}  "
              f"{r['pct_chg']:>8.2f}  {r['volume_ratio']:>8.1f}")
    if len(rows) > 20:
        print(f"  ... 还有 {len(rows)-20} 只")


if __name__ == "__main__":
    main()