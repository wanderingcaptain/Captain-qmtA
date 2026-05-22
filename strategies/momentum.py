"""
一进二打板 (Second Consecutive Limit-up) Momentum Strategy.

变更记录：
  v1.1  - 修复 API 调用泛滥：复用现货数据和日线数据
        - 复用 market_utils 的 is_limit_up()，消除 1.095 硬编码
        - 补充异常处理，记录完整打点日志
"""

from typing import List

import pandas as pd

from config import Config
from data.market_data import MarketData
from utils.market_utils import find_recent_limit_up_idx
from utils.exceptions import DataFetchError
from utils.logger import get_logger

logger = get_logger("strategies.momentum")


class SecondBoardMomentum:
    """
    一进二打板选股策略。
    过滤条件：
    1. 市值 < 100亿
    2. 过去 N 个交易日内有过涨停（活跃股性）
    3. 现价 > 最近一次涨停日的最低价（底线防守）
    """

    def __init__(self, market_data: MarketData):
        self.md = market_data
        self._stats: dict = {}

    # ------------------------------------------------------------------
    # 核心检查
    # ------------------------------------------------------------------
    def _check_market_cap(self, code: str) -> bool:
        """检查市值是否满足条件（使用缓存的个股信息）。"""
        try:
            cap = self.md.get_market_cap(code)
            return 0 < cap < Config.MOMENTUM.MAX_MARKET_CAP
        except Exception as e:
            logger.debug(f"{code} 市值获取失败: {e}")
            return False

    def _bars_pass_checks(self, code: str, current_price: float) -> bool:
        """
        组合检查：
        1. 获取日线检查涨停历史
        2. 确认现价高于底线
        """
        try:
            bars = self.md.get_daily_bars(code, count=Config.MOMENTUM.LIMIT_UP_LOOKBACK_DAYS)
        except DataFetchError as e:
            logger.debug(f"{code} 日线获取失败: {e}")
            return False

        if bars.empty or len(bars) < 2:
            return False

        # 查找最近一次涨停日
        limit_up_idx = find_recent_limit_up_idx(bars)
        if limit_up_idx is None:
            return False

        # 底线防守：现价需高于该涨停日的最低价
        limit_up_low = bars.iloc[limit_up_idx]["low"]
        if current_price <= limit_up_low:
            return False

        return True

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def run(self, candidates: List[str], spot_df: pd.DataFrame = None) -> List[str]:
        """
        运行策略，过滤预候选池中的股票。
        参数：
            candidates: 待筛选的代码列表
            spot_df: 可选的预取全市场行情（用于避免批量查价）
        """
        qualified: List[str] = []
        self._stats = {"market_cap_fail": 0, "bars_fail": 0, "passed": 0, "errors": 0}

        # 提取现价映射以加速检查
        price_map = {}
        if spot_df is not None and not spot_df.empty:
            for _, row in spot_df.iterrows():
                # 保留有/无前缀两种映射以策万全
                code_raw = str(row["code"])
                price_map[code_raw] = float(row["price"])
                for pfx in ("sh", "sz", "bj"):
                    if code_raw.startswith(pfx):
                        price_map[code_raw[len(pfx):]] = float(row["price"])

        for code in candidates:
            # 1. 查市值
            if not self._check_market_cap(code):
                self._stats["market_cap_fail"] += 1
                continue

            # 2. 获取现价
            current_price = price_map.get(code, 0.0)
            if current_price <= 0:
                try:
                    current_price = self.md.get_price(code)
                except Exception:
                    self._stats["errors"] += 1
                    continue

            # 3. K线检测
            if not self._bars_pass_checks(code, current_price):
                self._stats["bars_fail"] += 1
                continue

            qualified.append(code)
            self._stats["passed"] += 1

        logger.info(
            f"打板策略筛选完成：输入 {len(candidates)} 只，"
            f"通过 {self._stats['passed']} 只。拦截原因：市值超标={self._stats['market_cap_fail']}, "
            f"K线不符={self._stats['bars_fail']}, 异常={self._stats['errors']}"
        )

        return qualified