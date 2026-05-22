"""
策略抽象基类 — 统一买卖信号接口。
所有策略类继承此模块中的抽象类，保持 API 一致。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional

import pandas as pd


# ============================================================
# 信号类型枚举
# ============================================================
class SignalType(Enum):
    BUY = auto()
    SELL_FULL = auto()      # 全部卖出
    SELL_PARTIAL = auto()   # 部分卖出
    HOLD = auto()           # 持有，无操作


# ============================================================
# 信号数据类（替代原先的字符串返回值）
# ============================================================
@dataclass
class Signal:
    """
    交易信号对象。

    属性：
        type:       信号类型（BUY / SELL_FULL / SELL_PARTIAL / HOLD）
        reason:     触发原因，如 "stop_loss"、"vwap_support"
        confidence: 置信度 0.0 ~ 1.0（当前以规则驱动为主，默认 1.0）
        params:     附加参数，如 {"ratio": 0.5} 表示部分卖出比例
    """
    type: SignalType
    reason: str
    confidence: float = 1.0
    params: dict = field(default_factory=dict)

    # -------- 快捷构造 --------

    @classmethod
    def buy(cls, reason: str, confidence: float = 1.0) -> "Signal":
        return cls(SignalType.BUY, reason, confidence)

    @classmethod
    def sell_full(cls, reason: str) -> "Signal":
        return cls(SignalType.SELL_FULL, reason)

    @classmethod
    def sell_partial(cls, reason: str, ratio: float) -> "Signal":
        return cls(SignalType.SELL_PARTIAL, reason, params={"ratio": ratio})

    @classmethod
    def hold(cls) -> "Signal":
        return cls(SignalType.HOLD, "hold")

    # -------- 属性 --------

    @property
    def is_sell(self) -> bool:
        return self.type in (SignalType.SELL_FULL, SignalType.SELL_PARTIAL)

    @property
    def sell_ratio(self) -> float:
        """部分卖出比例，SELL_FULL 时返回 1.0。"""
        if self.type == SignalType.SELL_FULL:
            return 1.0
        return self.params.get("ratio", 1.0)

    def __bool__(self) -> bool:
        """非 HOLD 信号视为有效信号。"""
        return self.type != SignalType.HOLD


# ============================================================
# 抽象基类
# ============================================================
class BaseScreener(ABC):
    """盘后选股器基类。"""

    @abstractmethod
    def run(self, spot_df: Optional[pd.DataFrame] = None) -> List[str]:
        """
        运行选股流水线。
        参数：
            spot_df: 可选的预取全市场行情 DataFrame，避免内部重复拉取。
        返回：
            通过筛选的股票代码列表（无交易所前缀）。
        """


class BaseSignalEvaluator(ABC):
    """盘中信号评估器基类。"""

    @abstractmethod
    def evaluate(self, code: str, **ctx) -> Optional[Signal]:
        """
        评估单只股票的交易信号。
        参数：
            code: 股票代码
            ctx:  可选上下文（如当前价格、VWAP 等，避免重复查询）
        返回：
            Signal 对象，若无信号则返回 None 或 Signal.hold()。
        """
