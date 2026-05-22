"""
盘后选股运行脚本。
执行全市场过滤，生成候选股票池。

变更记录：
  v1.1  - 消除了 classify_candidates 中的重复逻辑，直接利用 screener.categories 缓存
        - 移除原先庞大且冗余的重复获取日线和重复计算逻辑
        - 移除 sys.path 强行插入的 hack（假定在项目根目录运行）
        - 使用 logger 替代 print
"""

import argparse
import json
import os
from datetime import date
from typing import Dict, List

import pandas as pd

from config import Config
from data.market_data import MarketData
from strategies.screener import DailyScreener
from strategies.momentum import SecondBoardMomentum
from utils.logger import setup_logger

logger = setup_logger("run_screening")


class CustomEncoder(json.JSONEncoder):
    """自定义 JSON 编码器，处理 Pandas 的 np.int64 / np.float64 等。"""
    def default(self, obj):
        if pd.isna(obj):
            return None
        if hasattr(obj, "item"):
            return obj.item()
        return super().default(obj)


def save_result(result_dict: Dict, date_str: str):
    """保存选股结果到 JSON 和 TXT。"""
    data_dir = Config.SYSTEM.DATA_DIR
    os.makedirs(data_dir, exist_ok=True)

    # 1. 详细 JSON 报告
    json_path = os.path.join(data_dir, f"screening_{date_str}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, ensure_ascii=False, indent=2, cls=CustomEncoder)
    logger.info(f"选股报告已保存至: {json_path}")

    # 2. 纯列表 TXT (供盘中加载)
    watchlist_path = os.path.join(data_dir, Config.SYSTEM.WATCHLIST_FILE)
    with open(watchlist_path, "w", encoding="utf-8") as f:
        for code in result_dict["all_candidates"]:
            f.write(f"{code}\n")
    logger.info(f"监控池代码已保存至: {watchlist_path}")


def run_screening(date_str: str = None):
    """
    运行全市场选股并保存结果。
    """
    if date_str is None:
        date_str = date.today().strftime("%Y%m%d")

    logger.info(f"========== 盘后选股开始 ({date_str}) ==========")
    md = MarketData()
    
    # 提前获取全市场基础行情，供后续共用
    try:
        spot_df = md.get_spot()
        logger.info(f"获取全市场基础行情成功，共 {len(spot_df)} 只股票")
    except Exception as e:
        logger.error(f"获取全市场行情失败: {e}")
        return

    # 1. 运行核心筛选器
    screener = DailyScreener(md)
    base_candidates = screener.run(spot_df=spot_df)

    if not base_candidates:
        logger.warning("核心筛选器未选出任何股票。")
        save_result({
            "date": date_str,
            "all_candidates": [],
            "classified": {},
            "momentum_pool": []
        }, date_str)
        return

    # 2. 运行打板策略过滤
    momentum = SecondBoardMomentum(md)
    momentum_pool = momentum.run(base_candidates, spot_df=spot_df)

    # 3. 整理分类结果（直接复用 screener 的缓存，消除原有数百行重复代码）
    classified: Dict[str, List[str]] = {}
    for code in base_candidates:
        cat = screener.categories.get(code, "其他")
        if cat not in classified:
            classified[cat] = []
        classified[cat].append(code)

    # 4. 构建报告
    result = {
        "date": date_str,
        "summary": {
            "total_candidates": len(base_candidates),
            "momentum_candidates": len(momentum_pool)
        },
        "classified": classified,
        "momentum_pool": momentum_pool,
        "all_candidates": base_candidates
    }

    # 打印简报
    logger.info("========== 选股结果摘要 ==========")
    for cat, codes in classified.items():
        logger.info(f"- {cat}: {len(codes)} 只")
    logger.info(f"- 打板备选池: {len(momentum_pool)} 只")
    logger.info("=================================")

    save_result(result, date_str)


def main():
    parser = argparse.ArgumentParser(description="QMT_THS 盘后选股运行脚本")
    parser.add_argument(
        "--date", 
        type=str, 
        help="指定运行日期 (YYYYMMDD)，默认当天"
    )
    args = parser.parse_args()
    
    try:
        run_screening(args.date)
    except KeyboardInterrupt:
        logger.info("用户中断选股运行")
    except Exception as e:
        logger.error(f"选股运行发生未捕获异常: {e}", exc_info=True)


if __name__ == "__main__":
    main()