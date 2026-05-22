"""
配置管理模块。
从 settings.toml 加载配置，支持环境变量覆盖。

变更记录：
  v1.1  - 重构配置类加载机制，引入 tomllib（或 tomli）
        - 将硬编码的配置常量改为动态属性
        - 补充类型检查与 validate 校验方法
"""

import os
import sys
from datetime import datetime, time
from typing import Any, Dict

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("缺少 TOML 解析库，请安装 tomli: pip install tomli", file=sys.stderr)
        sys.exit(1)


def _parse_time(time_str: str) -> time:
    """解析 HH:MM:SS 为 time 对象。"""
    return datetime.strptime(time_str, "%H:%M:%S").time()


class BaseConfigSection:
    """配置片段基类。"""

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def _get(self, key: str, default: Any = None) -> Any:
        # 支持环境变量覆盖：QMT_MACRO_ADVANCING_STOCKS_THRESHOLD
        env_key = f"QMT_{self.__class__.__name__.replace('Config', '').upper()}_{key.upper()}"
        if env_key in os.environ:
            val = os.environ[env_key]
            # 简单类型转换
            if isinstance(default, int): return int(val)
            if isinstance(default, float): return float(val)
            if isinstance(default, bool): return val.lower() in ("true", "1", "yes")
            return val
        return self._data.get(key, default)


class SystemConfig(BaseConfigSection):
    @property
    def DATA_DIR(self) -> str: return self._get("data_dir", "data")
    @property
    def LOG_DIR(self) -> str: return self._get("log_dir", "logs")
    @property
    def LOG_LEVEL(self) -> str: return self._get("log_level", "INFO")
    @property
    def WATCHLIST_FILE(self) -> str: return self._get("watchlist_file", "watchlist.txt")
    @property
    def POSITION_FILE(self) -> str: return self._get("position_file", "data/portfolio.json")
    @property
    def DATA_FETCH_INTERVAL_SECONDS(self) -> int: return self._get("data_fetch_interval_seconds", 3)


class TradingTimeConfig(BaseConfigSection):
    @property
    def MORNING_OPEN(self) -> time: return _parse_time(self._get("morning_open", "09:30:00"))
    @property
    def MORNING_CLOSE(self) -> time: return _parse_time(self._get("morning_close", "11:30:00"))
    @property
    def AFTERNOON_OPEN(self) -> time: return _parse_time(self._get("afternoon_open", "13:00:00"))
    @property
    def AFTERNOON_CLOSE(self) -> time: return _parse_time(self._get("afternoon_close", "14:57:00"))
    @property
    def CIRCUIT_BREAKER_START(self) -> time: return _parse_time(self._get("circuit_breaker_start", "09:30:00"))
    @property
    def CIRCUIT_BREAKER_END(self) -> time: return _parse_time(self._get("circuit_breaker_end", "09:40:00"))
    @property
    def BUY_WINDOW_1_START(self) -> time: return _parse_time(self._get("buy_window_1_start", "09:30:00"))
    @property
    def BUY_WINDOW_1_END(self) -> time: return _parse_time(self._get("buy_window_1_end", "10:40:00"))
    @property
    def BUY_WINDOW_2_START(self) -> time: return _parse_time(self._get("buy_window_2_start", "14:40:00"))
    @property
    def BUY_WINDOW_2_END(self) -> time: return _parse_time(self._get("buy_window_2_end", "14:55:00"))


class MacroConfig(BaseConfigSection):
    @property
    def ADVANCING_STOCKS_THRESHOLD(self) -> int: return self._get("advancing_stocks_threshold", 3000)
    @property
    def CIRCUIT_BREAKER_ADVANCING_WARNING(self) -> int: return self._get("circuit_breaker_advancing_warning", 3000)
    @property
    def CIRCUIT_BREAKER_ADVANCING_BELOW(self) -> int: return self._get("circuit_breaker_advancing_below", 4000)


class ScreenerConfig(BaseConfigSection):
    @property
    def VOLUME_RATIO_THRESHOLD(self) -> float: return self._get("volume_ratio_threshold", 2.5)
    @property
    def LIMIT_UP_LOOKBACK_DAYS(self) -> int: return self._get("limit_up_lookback_days", 15)
    @property
    def VOLUME_SURGE_MA_PERIOD(self) -> int: return self._get("volume_surge_ma_period", 30)
    @property
    def VOLUME_SURGE_MULTIPLE(self) -> float: return self._get("volume_surge_multiple", 2.0)
    @property
    def UPPER_SHADOW_MIN_RATIO(self) -> float: return self._get("upper_shadow_min_ratio", 2.0)
    @property
    def LOWER_SHADOW_MAX_RATIO(self) -> float: return self._get("lower_shadow_max_ratio", 0.2)
    @property
    def LOG_INTERVAL(self) -> int: return self._get("log_interval", 20)


class MomentumConfig(BaseConfigSection):
    @property
    def MAX_MARKET_CAP(self) -> float: return self._get("max_market_cap", 1e10)
    @property
    def LIMIT_UP_LOOKBACK_DAYS(self) -> int: return self._get("limit_up_lookback_days", 10)


class BuyConfig(BaseConfigSection):
    @property
    def MAX_OPEN_POSITIONS(self) -> int: return self._get("max_open_positions", 5)
    @property
    def VWAP_BAND_PERCENT(self) -> float: return self._get("vwap_band_percent", 0.005)
    @property
    def VWAP_CONFIRM_MINUTES(self) -> int: return self._get("vwap_confirm_minutes", 3)
    @property
    def VOLUME_LOOKBACK_MINUTES(self) -> int: return self._get("volume_lookback_minutes", 5)
    @property
    def VOLUME_SHRINK_RATIO(self) -> float: return self._get("volume_shrink_ratio", 0.5)
    @property
    def RAPID_RALLY_LOOKBACK_MINUTES(self) -> int: return self._get("rapid_rally_lookback_minutes", 3)
    @property
    def RAPID_RALLY_PRICE_PCT(self) -> float: return self._get("rapid_rally_price_pct", 0.03)
    @property
    def EARLY_SESSION_BASELINE_MINUTES(self) -> int: return self._get("early_session_baseline_minutes", 30)
    @property
    def RAPID_RALLY_VOLUME_MULTIPLE(self) -> float: return self._get("rapid_rally_volume_multiple", 3.0)
    @property
    def COOLING_PERIOD_MINUTES(self) -> int: return self._get("cooling_period_minutes", 15)


class SellConfig(BaseConfigSection):
    @property
    def STOP_LOSS_VWAP_PCT(self) -> float: return self._get("stop_loss_vwap_pct", 0.02)
    @property
    def TAKE_PROFIT_1_PCT(self) -> float: return self._get("take_profit_1_pct", 0.03)
    @property
    def TAKE_PROFIT_1_RATIO(self) -> float: return self._get("take_profit_1_ratio", 0.5)
    @property
    def TAKE_PROFIT_2_PCT(self) -> float: return self._get("take_profit_2_pct", 0.05)
    @property
    def TAKE_PROFIT_2_RATIO(self) -> float: return self._get("take_profit_2_ratio", 1.0)
    @property
    def RESISTANCE_VWAP_BAND_PCT(self) -> float: return self._get("resistance_vwap_band_pct", 0.01)
    @property
    def RESISTANCE_CONSECUTIVE_BARS(self) -> int: return self._get("resistance_consecutive_bars", 3)
    @property
    def RESISTANCE_COUNTER_LIMIT(self) -> int: return self._get("resistance_counter_limit", 2)
    @property
    def DIVERGENCE_VOLUME_RATIO_THRESHOLD(self) -> float: return self._get("divergence_volume_ratio_threshold", 3.0)
    @property
    def DIVERGENCE_GAIN_MIN_PCT(self) -> float: return self._get("divergence_gain_min_pct", 0.01)
    @property
    def DIVERGENCE_GAIN_MAX_PCT(self) -> float: return self._get("divergence_gain_max_pct", 0.025)
    @property
    def DIVERGENCE_DURATION_MINUTES(self) -> int: return self._get("divergence_duration_minutes", 5)
    @property
    def BREAKDOWN_CHECK_TIME(self) -> time: return _parse_time(self._get("breakdown_check_time", "14:50:00"))


class RiskConfig(BaseConfigSection):
    @property
    def MAX_CONSECUTIVE_LOSS_DAYS(self) -> int: return self._get("max_consecutive_loss_days", 2)
    @property
    def POSITION_CAP_AFTER_LOSS(self) -> float: return self._get("position_cap_after_loss", 0.5)
    @property
    def FORCED_LIQUIDATION_CONSECUTIVE_DAYS(self) -> int: return self._get("forced_liquidation_consecutive_days", 3)
    @property
    def BUY_SUSPEND_DAYS(self) -> int: return self._get("buy_suspend_days", 2)


class NotifyConfig(BaseConfigSection):
    @property
    def WECHAT_WEBHOOK(self) -> str: return self._get("wechat_webhook", "")
    @property
    def DINGTALK_WEBHOOK(self) -> str: return self._get("dingtalk_webhook", "")
    @property
    def TELEGRAM_BOT_TOKEN(self) -> str: return self._get("telegram_bot_token", "")
    @property
    def TELEGRAM_CHAT_ID(self) -> str: return self._get("telegram_chat_id", "")
    @property
    def RATE_LIMIT_MINUTES(self) -> int: return self._get("rate_limit_minutes", 5)


class Configuration:
    """全局配置单例。"""

    def __init__(self):
        # 尝试从项目根目录加载 settings.toml
        # 若未找到，则退化为默认值空字典
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # 优先加载 .env 文件中的环境变量
        try:
            from dotenv import load_dotenv
            env_path = os.path.join(root_dir, ".env")
            if os.path.exists(env_path):
                load_dotenv(env_path)
        except ImportError:
            pass
            
        toml_path = os.path.join(root_dir, "config", "settings.toml")
        
        self._raw_data = {}
        if os.path.exists(toml_path):
            with open(toml_path, "rb") as f:
                self._raw_data = tomllib.load(f)

        self.SYSTEM = SystemConfig(self._raw_data.get("system", {}))
        self.TRADING_TIME = TradingTimeConfig(self._raw_data.get("trading_time", {}))
        self.MACRO = MacroConfig(self._raw_data.get("macro", {}))
        self.SCREENER = ScreenerConfig(self._raw_data.get("screener", {}))
        self.MOMENTUM = MomentumConfig(self._raw_data.get("momentum", {}))
        self.BUY = BuyConfig(self._raw_data.get("buy", {}))
        self.SELL = SellConfig(self._raw_data.get("sell", {}))
        self.RISK = RiskConfig(self._raw_data.get("risk", {}))
        self.NOTIFY = NotifyConfig(self._raw_data.get("notify", {}))

    def validate(self):
        """校验配置参数是否合理。"""
        assert 0 <= self.SELL.TAKE_PROFIT_1_RATIO <= 1, "止盈比例需在 0-1 之间"
        assert self.BUY.MAX_OPEN_POSITIONS > 0, "最大持仓数必须大于 0"
        # 其他业务约束可在此补充...


# 全局单例
Config = Configuration()
Config.validate()

# 导出兼容旧代码的别名
SystemConfig = Config.SYSTEM

__all__ = ["Config", "SystemConfig"]