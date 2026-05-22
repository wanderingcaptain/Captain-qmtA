"""
独立量比筛选脚本。
盘中快速筛选异动量比股票。

变更记录：
  v1.1  - 修复 Bug #7：量比阈值使用 Config.SCREENER.VOLUME_RATIO_THRESHOLD，而非硬编码的 2.0
        - 移除私有方法调用，改用 md.get_volume_ratios() 和 md.get_spot()
        - 补充非剔除股票（ST/科创板等）的过滤逻辑
        - 移除 sys.path hack
        - 替换 print 为 logger
"""

import json
import os
from datetime import datetime

from config import Config
from data.market_data import MarketData
from utils.market_utils import is_excluded_stock
from utils.logger import setup_logger

logger = setup_logger("run_volume")


def main():
    logger.info("========== 开始盘中量比筛选 ==========")
    md = MarketData()
    
    threshold = Config.SCREENER.VOLUME_RATIO_THRESHOLD
    logger.info(f"读取配置阈值: 量比 > {threshold}")

    try:
        spot = md.get_spot()
        if spot.empty:
            logger.error("全市场行情获取失败，退出筛选")
            return
            
        logger.info(f"获取最新量比数据...")
        df = md.get_volume_ratios()
        if df.empty:
            logger.error("量比数据获取失败，退出筛选")
            return
    except Exception as e:
        logger.error(f"数据获取异常: {e}", exc_info=True)
        return

    # 过滤阈值
    filtered = df[df["volume_ratio"] >= threshold].copy()
    logger.info(f"全市场共有 {len(filtered)} 只股票量比达标。进行排除项过滤...")

    results = []
    for _, row in filtered.iterrows():
        code = str(row["code"])
        name = str(row["name"])
        
        # 补全基础防坑过滤（ST、科创、北交所）
        if is_excluded_stock(code, name):
            continue
            
        # 从 spot 获取涨跌幅和价格（使用最新实时数据）
        match = spot[spot["code"].str.endswith(code)]
        if not match.empty:
            price = float(match.iloc[0]["price"])
            pct_chg = float(match.iloc[0]["pct_chg"])
        else:
            price = row.get("price", 0.0)
            pct_chg = row.get("pct_chg", 0.0)

        results.append({
            "code": code,
            "name": name,
            "price": price,
            "pct_chg": pct_chg,
            "volume_ratio": float(row["volume_ratio"])
        })

    # 按量比降序
    results.sort(key=lambda x: x["volume_ratio"], reverse=True)

    data_dir = Config.SYSTEM.DATA_DIR
    os.makedirs(data_dir, exist_ok=True)
    
    time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(data_dir, f"volume_alert_{time_str}.json")
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info(f"筛选完成！共得到 {len(results)} 只股票。")
    logger.info(f"结果已保存至: {out_path}")
    
    # 打印 Top 10
    logger.info("========== Top 10 量比激增股票 ==========")
    for i, item in enumerate(results[:10]):
        logger.info(
            f"{i+1:2d}. {item['code']} {item['name'][:4]:<4} "
            f"现价:{item['price']:>6.2f}  "
            f"涨幅:{item['pct_chg']:>6.2f}%  "
            f"量比:{item['volume_ratio']:>5.2f}"
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("用户中断运行")