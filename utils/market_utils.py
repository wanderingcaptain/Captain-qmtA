"""
市场数据公共工具函数。
提取多处重复的代码逻辑，作为无副作用的纯函数供全局使用。
"""

from typing import Optional
import pandas as pd


# ============================================================
# 代码格式转换
# ============================================================

def to_sina_code(code: str) -> str:
    """
    将原始股票代码转为 Sina 格式（加交易所前缀）。
    "600519"  → "sh600519"
    "000001"  → "sz000001"
    "sh600519" → "sh600519"（已有前缀则不变）
    """
    code_str = str(code).strip()
    if code_str.startswith(("sh", "sz", "bj")):
        return code_str
    if code_str.startswith(("6", "9")):
        return f"sh{code_str}"
    if code_str.startswith(("0", "3", "2")):
        return f"sz{code_str}"
    # 默认归 sh（指数、其他）
    return f"sh{code_str}"


def strip_code_prefix(code: str) -> str:
    """
    去除交易所前缀，返回裸代码。
    "sh600519" → "600519"
    "600519"   → "600519"（无前缀则不变）
    """
    for prefix in ("sh", "sz", "bj"):
        if code.startswith(prefix):
            return code[len(prefix):]
    return code


def normalize_code(code: str) -> str:
    """确保代码无前缀（标准化为裸代码）。别名 strip_code_prefix。"""
    return strip_code_prefix(code)


# ============================================================
# 行情判断
# ============================================================

def is_limit_up(close: float, prev_close: float, threshold: float = 0.095) -> bool:
    """
    判断是否涨停。
    A 股普通股票涨停幅度为 +10%（≥9.5% 即视为涨停，考虑精度误差）。
    科创板/创业板 (±20%) 请传入 threshold=0.195。

    参数：
        close: 当日收盘价
        prev_close: 前日收盘价
        threshold: 涨幅阈值，默认 0.095 (9.5%)
    """
    if prev_close <= 0:
        return False
    return close >= prev_close * (1 + threshold)


def find_recent_limit_up_idx(bars: pd.DataFrame, threshold: float = 0.095) -> Optional[int]:
    """
    在日线 DataFrame 中查找最近一次涨停的行索引。
    bars 需要包含 'close' 列，且按时间升序排列。
    返回 None 表示未找到。
    """
    for i in range(len(bars) - 1, 0, -1):
        if is_limit_up(bars.iloc[i]["close"], bars.iloc[i - 1]["close"], threshold):
            return i
    return None


def has_recent_limit_up(bars: pd.DataFrame, threshold: float = 0.095) -> bool:
    """检查日线数据中是否存在涨停记录。"""
    return find_recent_limit_up_idx(bars, threshold) is not None


# ============================================================
# A 股交易规则
# ============================================================

def round_lot(shares: int) -> int:
    """
    向下取整为 100 股整数倍（A 股最小交易单位）。
    0 保持为 0。
    """
    return (shares // 100) * 100


def calc_position_size(
    cash: float,
    price: float,
    cap: float = 1.0,
    max_stocks: int = 5,
) -> int:
    """
    计算单只股票仓位（股数）。
    参数：
        cash: 可用现金
        price: 目标价格
        cap: 仓位上限系数 (0.0 ~ 1.0)
        max_stocks: 最大同时持仓只数
    返回：
        整数股数（已按 100 股取整）
    """
    if price <= 0 or max_stocks <= 0:
        return 0
    per_stock_cash = cash * cap / max_stocks
    shares = int(per_stock_cash / price)
    return round_lot(shares)


def is_excluded_stock(code: str, name: str) -> bool:
    """
    判断是否应排除股票（ST/科创板/北交所）。
    提取自 DailyScreener._is_excluded()，供全局复用。

    排除条件：
      - 名称含 "ST" 或 "*ST"
      - 代码以 688/689 开头（科创板）
      - 代码以 bj 前缀或 8 开头（北交所）
    """
    if "ST" in name:
        return True
    raw = strip_code_prefix(code)
    if raw.startswith(("688", "689")):
        return True
    if code.startswith("bj") or raw.startswith("8"):
        return True
    return False
