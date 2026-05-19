"""
盘后选股脚本 — 运行完整选股流水线，将结果分类保存到 screening_results/ 目录。

用法:
  .venv/bin/python run_screening.py                    # 选今天
  .venv/bin/python run_screening.py --date 20260519    # 指定日期

输出:
  screening_results/YYYY-MM-DD.json   (完整分类数据)
  screening_results/YYYY-MM-DD.txt    (可读摘要)
"""

import argparse
import json
import os
import sys
from datetime import datetime, date
from typing import Dict, List, Set, Tuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.market_data import MarketData
from strategies.screener import DailyScreener
from strategies.momentum import SecondBoardMomentum


RESULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screening_results")


def get_limit_up_map(md: MarketData, date_str: str) -> Dict[str, dict]:
    """获取当日涨停池明细（含连板数、行业等）。"""
    try:
        df = md.get_limit_up_pool(trade_date=date_str)
        if df.empty:
            return {}
        result = {}
        for _, row in df.iterrows():
            result[str(row["code"])] = {
                "consecutive_boards": int(row.get("consecutive_boards", 0)),
                "first_seal_time": str(row.get("first_seal_time", "")),
                "last_seal_time": str(row.get("last_seal_time", "")),
                "blast_count": int(row.get("blast_count", 0)),
                "seal_amount": float(row.get("seal_amount", 0)),
                "turnover_rate": float(row.get("turnover_rate", 0)),
                "total_market_cap": float(row.get("total_market_cap", 0)),
                "industry": str(row.get("industry", "")),
            }
        return result
    except Exception as e:
        print(f"  [Warn] 涨停池获取失败: {e}")
        return {}


def get_volume_ratio_map(md: MarketData) -> Dict[str, float]:
    """获取全市场量比数据。"""
    try:
        df = md._get_em_spot_volume_ratios()
        if df.empty:
            return {}
        result = {}
        for _, row in df.iterrows():
            result[str(row["code"])] = float(row["volume_ratio"])
        return result
    except Exception as e:
        print(f"  [Warn] 量比获取失败: {e}")
        return {}


def get_spot_info(md: MarketData) -> Dict[str, dict]:
    """获取全市场行情（价格、涨跌幅、名称）。"""
    df = md._get_spot()
    result = {}
    for _, row in df.iterrows():
        raw_code = str(row["code"])
        # Strip exchange prefix to match bare codes from screener
        for prefix in ("sh", "sz", "bj"):
            if raw_code.startswith(prefix):
                raw_code = raw_code[len(prefix):]
                break
        result[raw_code] = {
            "name": row["name"],
            "price": float(row["price"]),
            "pct_chg": float(row["pct_chg"]),
            "volume": float(row["volume"]),
            "amount": float(row["amount"]),
        }
    return result


def classify_candidates(
    md: MarketData,
    candidates: List[str],
    date_str: str,
) -> Dict[str, list]:
    """
    对选中的候选股做详细分类。
    返回：{类别: [{code, name, price, ...}]}
    """
    spot_map = get_spot_info(md)
    limit_up_map = get_limit_up_map(md, date_str)
    vol_ratio_map = get_volume_ratio_map(md)

    categories: Dict[str, list] = {
        "涨停板": [],
        "近期涨停_量能突破": [],
        "量能突破": [],
        "仙人指路": [],
    }
    already_classified: Set[str] = set()

    # 1) 涨停板（从涨停池来的，带连板数）
    for code in candidates:
        if code in limit_up_map:
            info = limit_up_map[code]
            spot = spot_map.get(code, {})
            categories["涨停板"].append({
                "code": code,
                "name": spot.get("name", ""),
                "price": spot.get("price", 0),
                "pct_chg": spot.get("pct_chg", 0),
                "consecutive_boards": info["consecutive_boards"],
                "first_seal_time": info["first_seal_time"],
                "blast_count": info["blast_count"],
                "seal_amount": info["seal_amount"],
                "turnover_rate": info["turnover_rate"],
                "total_market_cap": info["total_market_cap"],
                "industry": info["industry"],
                "volume_ratio": vol_ratio_map.get(code, 0),
            })
            already_classified.add(code)

    # 2) 非涨停的候选 → 逐个检查日线确定入选原因
    remaining = [c for c in candidates if c not in already_classified]
    for code in remaining:
        spot = spot_map.get(code, {})
        base = {
            "code": code,
            "name": spot.get("name", ""),
            "price": spot.get("price", 0),
            "pct_chg": spot.get("pct_chg", 0),
            "volume_ratio": vol_ratio_map.get(code, 0),
        }

        # 检查日线
        try:
            bars = md.get_daily_bars(code, count=20)
            if bars is not None and len(bars) >= 2:
                today = bars.iloc[-1]
                yesterday = bars.iloc[-2]

                # 近期涨停
                has_recent_limit_up = False
                for i in range(1, len(bars)):
                    if bars.iloc[i]["close"] >= bars.iloc[i - 1]["close"] * 1.095:
                        has_recent_limit_up = True
                        break

                if has_recent_limit_up:
                    base["category"] = "近期涨停_量能突破"
                    categories["近期涨停_量能突破"].append(base)
                    continue

                # 量能突破（今日量 > 2× MA30 均量）
                if len(bars) >= 30:
                    ma_vol = bars.iloc[-31:-1]["volume"].mean()
                    if ma_vol > 0 and today["volume"] >= ma_vol * 2:
                        base["category"] = "量能突破"
                        base["today_volume"] = float(today["volume"])
                        base["ma30_volume"] = float(ma_vol)
                        categories["量能突破"].append(base)
                        continue

                # 仙人指路
                if len(bars) >= 3:
                    body = abs(today["open"] - today["close"])
                    if body > 0:
                        upper_shadow = today["high"] - max(today["open"], today["close"])
                        lower_shadow = min(today["open"], today["close"]) - today["low"]
                        if (
                            upper_shadow > 2 * body
                            and lower_shadow < 0.2 * body
                            and today["volume"] > yesterday["volume"]
                        ):
                            base["category"] = "仙人指路"
                            base["upper_shadow_ratio"] = float(upper_shadow / body)
                            categories["仙人指路"].append(base)
                            continue

                # 如果没有匹配任何已知条件，归入"其他"
                base["category"] = "其他"
                categories.setdefault("其他", []).append(base)
            else:
                base["category"] = "其他"
                categories.setdefault("其他", []).append(base)
        except Exception:
            base["category"] = "其他"
            categories.setdefault("其他", []).append(base)

    # 移除空类别
    return {k: v for k, v in categories.items() if v}


def run_screening(date_str: str = None) -> dict:
    """
    运行完整选股流水线。

    参数:
        date_str: 日期 YYYYMMDD，None 则取今天

    返回:
        包含日期、分类结果、统计的 dict
    """
    if date_str is None:
        date_str = date.today().strftime("%Y%m%d")
        date_display = date.today().isoformat()
    else:
        date_display = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

    print(f"{'='*60}")
    print(f"  盘后选股 — {date_display}")
    print(f"{'='*60}")

    md = MarketData()
    t0 = datetime.now()

    # 1) 日线选股
    screener = DailyScreener(md)
    candidates = screener.run()
    t1 = datetime.now()
    print(f"\n  日线选股完成: {len(candidates)} 只 ({t1 - t0})")

    # 2) 一进二打板
    momentum = SecondBoardMomentum(md)
    momentum_candidates = momentum.run(candidates)
    t2 = datetime.now()
    print(f"  一进二打板: {len(momentum_candidates)} 只 ({t2 - t1})")

    # 3) 详细分类
    print(f"\n  正在获取详细分类信息...")
    categories = classify_candidates(md, candidates, date_str)

    # 4) 构建输出
    # 统计各类别数量
    stats = {"total": len(candidates), "momentum": len(momentum_candidates)}
    for cat_name, items in categories.items():
        stats[cat_name] = len(items)

    result = {
        "date": date_display,
        "run_time": datetime.now().isoformat(),
        "stats": stats,
        "categories": categories,
        "momentum_candidates": momentum_candidates,
    }
    return result


def save_result(result: dict):
    """保存结果到 screening_results/ 目录。"""
    os.makedirs(RESULT_DIR, exist_ok=True)
    date_str = result["date"]
    base = os.path.join(RESULT_DIR, date_str)

    # JSON
    json_path = f"{base}.json"
    # 将 numpy/pandas 类型转为原生 Python 类型
    class CustomEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (pd.Timestamp,)):
                return str(obj)
            if isinstance(obj, (pd.Series, pd.DataFrame)):
                return obj.to_dict()
            return super().default(obj)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, cls=CustomEncoder)

    # TXT 可读摘要
    txt_path = f"{base}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"盘后选股报告 — {result['date']}\n")
        f.write(f"{'='*60}\n\n")
        f.write(f"运行时间: {result['run_time']}\n")
        f.write(f"候选总数: {result['stats']['total']}\n\n")

        for cat_name, items in result["categories"].items():
            f.write(f"─ {cat_name} ({len(items)} 只) ─\n")
            f.write(f"{'代码':>8}  {'名称':<8}  {'价格':>8}  {'涨幅%':>8}")
            # 根据类别动态加附加列
            extra_cols = []
            if cat_name == "涨停板":
                extra_cols = ["连板", "行业"]
                f.write(f"  {'连板':>4}  {'行业':<8}")
            elif cat_name in ("量能突破", "近期涨停_量能突破"):
                extra_cols = ["量比"]
                f.write(f"  {'量比':>8}")
            f.write("\n" + "─" * (40 + len(extra_cols) * 12) + "\n")

            for item in items:
                f.write(f"{item['code']:>8}  {item.get('name',''):<8}  "
                        f"{item['price']:>8.2f}  {item.get('pct_chg',0):>8.2f}")
                if cat_name == "涨停板":
                    f.write(f"  {item.get('consecutive_boards',0):>4}  {item.get('industry',''):<8}")
                elif "volume_ratio" in item:
                    f.write(f"  {item['volume_ratio']:>8.1f}")
                f.write("\n")
            f.write("\n")

        f.write(f"\n一进二打板候选 ({result['stats']['momentum']} 只):\n")
        f.write(", ".join(result["momentum_candidates"]) + "\n")

    print(f"\n  结果已保存:")
    print(f"    JSON: {json_path}")
    print(f"    TXT:  {txt_path}")
    return json_path, txt_path


def main():
    parser = argparse.ArgumentParser(description="盘后选股脚本")
    parser.add_argument("--date", type=str, default=None,
                        help="日期 YYYYMMDD（默认取今天）")
    args = parser.parse_args()

    result = run_screening(args.date)
    save_result(result)

    # 屏幕输出摘要
    print(f"\n{'='*60}")
    print(f"  选股完成 — {result['date']}")
    print(f"{'='*60}")
    for cat_name, items in result["categories"].items():
        print(f"  {cat_name}: {len(items)} 只")
    print(f"  一进二打板: {result['stats']['momentum']} 只")
    print(f"  合计: {result['stats']['total']} 只")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()