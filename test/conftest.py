"""
Pytest Fixtures — 为整个测试框架提供可复用的 mock 数据和组件。
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock

from data.market_data import MarketData
from data.portfolio import Portfolio, PositionState
from strategies.base import Signal, SignalType
from config import Config


@pytest.fixture
def sample_spot_df() -> pd.DataFrame:
    """Mock 全市场现货数据"""
    return pd.DataFrame([
        {"code": "600519", "name": "贵州茅台", "price": 1800.0, "pct_chg": 1.2, "volume": 10000},
        {"code": "000001", "name": "平安银行", "price": 10.5, "pct_chg": -0.5, "volume": 50000},
        {"code": "688001", "name": "华兴源创", "price": 35.0, "pct_chg": 5.0, "volume": 2000},
        {"code": "000999", "name": "*ST测试", "price": 1.5, "pct_chg": 4.5, "volume": 1000},
    ])


@pytest.fixture
def sample_bars_df() -> pd.DataFrame:
    """Mock 日线 K 线数据"""
    dates = pd.date_range(start="2026-05-01", periods=10, freq="B")
    df = pd.DataFrame({
        "date": dates,
        "open": [10.0] * 10,
        "high": [11.0] * 10,
        "low": [9.0] * 10,
        "close": [10.5] * 10,
        "volume": [10000, 12000, 11000, 9000, 10500, 30000, 32000, 31000, 35000, 33000] # 后5天放量
    })
    # 强制让最后一天涨停（10.5 -> 11.55，正好 +10%）
    df.loc[9, "close"] = 11.55
    df.loc[8, "close"] = 10.5
    return df


@pytest.fixture
def mock_market_data(sample_spot_df, sample_bars_df) -> MarketData:
    """提供带有 mock API 返回值的 MarketData 实例。"""
    md = MarketData()
    md._init_proxy = MagicMock()
    
    md.get_spot = MagicMock(return_value=sample_spot_df)
    md.get_volume_ratios = MagicMock(return_value=pd.DataFrame([
        {"code": "000001", "name": "平安银行", "price": 10.5, "pct_chg": -0.5, "volume_ratio": 1.2},
        {"code": "600519", "name": "贵州茅台", "price": 1800.0, "pct_chg": 1.2, "volume_ratio": 3.5}, # 达标
    ]))
    
    md.get_stock_info = MagicMock(return_value={"总市值": 50_0000_0000}) # 50亿
    md.get_market_cap = MagicMock(return_value=50_0000_0000)
    
    md.get_limit_up_pool = MagicMock(return_value=pd.DataFrame([
        {"code": "000002", "name": "万科A", "price": 8.0, "pct_chg": 10.0}
    ]))
    
    md.get_daily_bars = MagicMock(return_value=sample_bars_df)
    md.get_minute_bars = MagicMock(return_value=pd.DataFrame())
    
    md.get_vwap = MagicMock(return_value=10.0)
    md.get_price = MagicMock(return_value=10.5)
    md.get_volume_ratio = MagicMock(return_value=1.5)
    
    md.get_market_advancing_declining = MagicMock(return_value=(3500, 1000, 500))
    md.is_trading_time = MagicMock(return_value=True)
    md.is_market_open_today = MagicMock(return_value=True)
    
    return md


@pytest.fixture
def mock_portfolio(tmp_path) -> Portfolio:
    """提供一个使用临时目录的干净 Portfolio"""
    # 覆盖配置路径，使其指向临时目录
    original_pos_file = Config.SYSTEM.POSITION_FILE
    Config.SYSTEM._data["position_file"] = str(tmp_path / "portfolio.json")
    
    p = Portfolio()
    p.cash = 100000.0
    
    yield p
    
    # 恢复配置
    Config.SYSTEM._data["position_file"] = original_pos_file


@pytest.fixture
def dummy_position() -> PositionState:
    """提供一个标准的持仓状态对象用于测试"""
    return PositionState(
        code="600519",
        entry_price=10.0,
        current_quantity=1000,
        entry_time="2026-05-22T09:30:00",
        vwap_at_entry=10.0,
        trigger_reason="vwap_support"
    )
