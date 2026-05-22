"""
盘后选股器 — 扫描全市场 A 股，筛选进入核心股票池的标的。

变更记录：
  v1.1  - 实现 BaseScreener 接口
        - 复用 market_utils 的公共函数（去重）
        - 引入 ThreadPoolExecutor 实现 Phase 3 日线并发拉取，大幅加速
        - 补充完整的异常处理，修复静默吞噬异常的 Bug
        - 替换 print 为 logger
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from config import Config
from data.market_data import MarketData
from strategies.base import BaseScreener
from utils.market_utils import is_excluded_stock, normalize_code, has_recent_limit_up
from utils.exceptions import DataFetchError
from utils.logger import get_logger

logger = get_logger("strategies.screener")


class DailyScreener(BaseScreener):
    """
    盘后选股引擎。
    包含：涨停池、量比激增、仙人指路、日线均量突破 等形态筛选。
    """

    def __init__(self, market_data: MarketData):
        self.md = market_data
        self._stats: Dict[str, int] = {}
        # 缓存每个股票的分类信息，供 run_screening.py 等外部脚本复用
        self.categories: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Phase 0: 涨停池
    # ------------------------------------------------------------------
    def _get_limit_up_candidates(self) -> Set[str]:
        """获取当日涨停池，自动加入候选。"""
        today_str = date.today().strftime("%Y%m%d")
        valid = set()
        try:
            df = self.md.get_limit_up_pool(trade_date=today_str)
            if df.empty:
                return valid

            for _, row in df.iterrows():
                code = str(row["code"])
                name = str(row["name"])
                if is_excluded_stock(code, name):
                    continue
                valid.add(code)
                self.categories[code] = "涨停板"
            return valid
        except DataFetchError as e:
            logger.warning(f"获取涨停池失败: {e}")
            return valid

    # ------------------------------------------------------------------
    # Phase 1: 基础行情过滤 (排除 ST/科创/北交)
    # ------------------------------------------------------------------
    def _prepare_spot_index(self, spot_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """从全市场行情中筛选出非排除股票。"""
        if spot_df is not None:
            spot = spot_df
        else:
            try:
                spot = self.md.get_spot()
            except DataFetchError as e:
                logger.error(f"获取全市场行情失败: {e}")
                return pd.DataFrame()

        if spot.empty:
            return spot

        # DataFrame column is "name" and "code"
        exclude_mask = spot.apply(
            lambda r: is_excluded_stock(str(r["code"]), str(r["name"])), axis=1
        )
        return spot[~exclude_mask].copy()

    # ------------------------------------------------------------------
    # Phase 2: 量比预筛
    # ------------------------------------------------------------------
    def _get_volume_ratio_candidates(self, spot: pd.DataFrame) -> Set[str]:
        """基于 EM push2 获取全市场量比。"""
        candidates: Set[str] = set()
        try:
            em = self.md.get_volume_ratios()
            if em.empty:
                logger.warning("EM 量比 API 返回为空，跳过量比初筛")
                return candidates
        except Exception as e:
            logger.warning(f"EM 量比获取异常: {e}，跳过该步过滤")
            return candidates

        threshold = Config.SCREENER.VOLUME_RATIO_THRESHOLD
        for _, row in em.iterrows():
            code = str(row["code"])
            vol_ratio = row["volume_ratio"]
            if vol_ratio is None or vol_ratio <= threshold:
                continue
            
            # 从 spot 中确认代码存在（且未被排除）
            match = spot[spot["code"].str.endswith(code)]
            if not match.empty:
                bare_code = normalize_code(match.iloc[0]["code"])
                candidates.add(bare_code)
                
        return candidates

    # ------------------------------------------------------------------
    # Phase 3: 日线级别形态确认
    # ------------------------------------------------------------------
    def _check_daily_patterns(self, code: str) -> Optional[str]:
        """
        拉取单只股票的日线，检查三种模式：
        1. 近期涨停
        2. 日均量突破（今天 > 2*MA30）
        3. 仙人指路形态
        返回匹配的模式名称（"近期涨停_量能突破"、"量能突破"、"仙人指路"），若全不匹配返回 None。
        """
        try:
            # 统一拉 35 天日线以满足 MA30 计算需求
            bars = self.md.get_daily_bars(code, count=35)
        except DataFetchError as e:
            logger.debug(f"{code} 日线获取失败: {e}")
            return None

        if bars.empty or len(bars) < 3:
            return None

        today = bars.iloc[-1]
        yesterday = bars.iloc[-2]

        # 模式 1: 近期涨停（看最近 N 天）
        lookback = min(len(bars), Config.SCREENER.LIMIT_UP_LOOKBACK_DAYS + 1)
        recent_bars = bars.tail(lookback).reset_index(drop=True)
        if has_recent_limit_up(recent_bars):
            return "近期涨停_量能突破"

        # 模式 2: 量能突破
        if len(bars) >= Config.SCREENER.VOLUME_SURGE_MA_PERIOD + 1:
            period = Config.SCREENER.VOLUME_SURGE_MA_PERIOD
            ma_vol = bars.iloc[-(period + 1): -1]["volume"].mean()
            if ma_vol > 0 and today["volume"] >= ma_vol * Config.SCREENER.VOLUME_SURGE_MULTIPLE:
                return "量能突破"

        # 模式 3: 仙人指路
        body = abs(today["open"] - today["close"])
        if body > 0:
            upper_shadow = today["high"] - max(today["open"], today["close"])
            lower_shadow = min(today["open"], today["close"]) - today["low"]
            if (
                upper_shadow > Config.SCREENER.UPPER_SHADOW_MIN_RATIO * body
                and lower_shadow < Config.SCREENER.LOWER_SHADOW_MAX_RATIO * body
                and today["volume"] > yesterday["volume"]
            ):
                return "仙人指路"

        return None

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def run(self, spot_df: Optional[pd.DataFrame] = None) -> List[str]:
        """执行完整筛选流水线，返回候选代码。"""
        self._stats = {
            "limit_up": 0, "volume_ratio": 0, "daily_confirmed": 0,
            "fairy_finger": 0, "errors": 0
        }
        self.categories.clear()

        # [Phase 0] 涨停池（直接入选）
        logger.info("[Phase 0] 获取涨停池...")
        candidates = self._get_limit_up_candidates()
        self._stats["limit_up"] = len(candidates)

        # [Phase 1] 现货筛选
        logger.info("[Phase 1] 准备全市场数据，过滤 ST/科创板/北交所...")
        spot = self._prepare_spot_index(spot_df)
        if spot.empty:
            logger.error("全市场行情为空，无法继续筛选")
            return sorted(list(candidates))
            
        remaining_count = len(spot) - len(candidates)
        if remaining_count <= 0:
            return sorted(list(candidates))

        # [Phase 2] 量比预筛
        logger.info(f"[Phase 2] 对 {remaining_count} 只股票进行量比检查...")
        vol_candidates = self._get_volume_ratio_candidates(spot)
        self._stats["volume_ratio"] = len(vol_candidates)
        logger.info(f"  > 量比达标: {len(vol_candidates)} 只")

        # 剔除已在涨停池中的
        to_check = vol_candidates - candidates
        logger.info(f"[Phase 3] 对 {len(to_check)} 只股票进行日线形态并发确认...")

        # [Phase 3] 并发日线检查
        # 优化点：使用线程池并发，限制并发数为 15 以防止 Sina 封 IP
        futures_map = {}
        processed = 0
        
        with ThreadPoolExecutor(max_workers=15) as executor:
            for code in to_check:
                fut = executor.submit(self._check_daily_patterns, code)
                futures_map[fut] = code

            for fut in as_completed(futures_map):
                code = futures_map[fut]
                processed += 1
                try:
                    category = fut.result()
                    if category:
                        candidates.add(code)
                        self.categories[code] = category
                        if category == "仙人指路":
                            self._stats["fairy_finger"] += 1
                        else:
                            self._stats["daily_confirmed"] += 1
                except Exception as e:
                    self._stats["errors"] += 1
                    logger.debug(f"{code} 并发检查异常: {e}")

                if processed % Config.SCREENER.LOG_INTERVAL == 0:
                    logger.info(
                        f"  > 进度: {processed}/{len(to_check)} "
                        f"| 累计选中: {len(candidates)} | 错误: {self._stats['errors']}"
                    )

        logger.info(
            f"选股完成: 共 {len(candidates)} 只候选 "
            f"(涨停={self._stats['limit_up']}, "
            f"日线确认={self._stats['daily_confirmed']}, "
            f"仙人指路={self._stats['fairy_finger']})"
        )

        return sorted(list(candidates))