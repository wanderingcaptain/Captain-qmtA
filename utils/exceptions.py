"""
QMT_THS 自定义异常体系。
用于区分网络错误、数据错误、业务逻辑错误，便于上层精确处理。
"""


class QMTError(Exception):
    """系统基础异常，所有自定义异常均继承自此类。"""


class DataFetchError(QMTError):
    """网络请求或 API 数据获取失败。"""


class DataValidationError(QMTError):
    """数据格式或内容校验失败（如列缺失、类型不符）。"""


class RateLimitError(DataFetchError):
    """API 限流（返回 HTML 或 429）。"""


class StrategyError(QMTError):
    """策略执行过程中的逻辑异常。"""


class RiskControlError(QMTError):
    """风控模块触发的异常（强制平仓、暂停买入等）。"""


class ConfigError(QMTError):
    """配置错误（参数缺失、格式非法、范围越界）。"""
