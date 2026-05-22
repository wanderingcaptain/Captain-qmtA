"""
盘后选股器与打板策略测试。
全面迁移至 pytest 框架，使用 mock 数据脱离真实网络。
"""

import pytest
from strategies.screener import DailyScreener
from strategies.momentum import SecondBoardMomentum


def test_is_excluded_stock(mock_market_data):
    """测试排除 ST、科创板、北交所股票。"""
    screener = DailyScreener(mock_market_data)
    # mock 中的数据：
    # "600519" 贵州茅台 (正常)
    # "000001" 平安银行 (正常)
    # "688001" 华兴源创 (科创板，应排除)
    # "000999" *ST测试 (ST，应排除)
    
    spot = mock_market_data.get_spot()
    filtered = screener._prepare_spot_index(spot)
    
    codes = filtered["code"].tolist()
    assert "600519" in codes
    assert "000001" in codes
    assert "688001" not in codes
    assert "000999" not in codes


def test_screener_run_pipeline(mock_market_data, sample_spot_df):
    """测试 DailyScreener 完整流水线。"""
    screener = DailyScreener(mock_market_data)
    
    # 模拟 run 的完整流程
    candidates = screener.run(spot_df=sample_spot_df)
    
    # 根据 mock 数据预期：
    # 涨停池包含 000002
    # 量比通过的有 600519
    # 所以 candidates 至少应包含 000002 和 600519（假设它们通过了日线模式，这里我们 mock_market_data 的日线会让其通过 量能突破 或 近期涨停）
    
    assert "000002" in candidates
    
    stats = screener._stats
    assert stats["limit_up"] == 1
    # 600519 的量比是 3.5 > 2.5
    assert stats["volume_ratio"] == 1 


def test_momentum_strategy(mock_market_data, sample_spot_df):
    """测试一进二打板策略。"""
    momentum = SecondBoardMomentum(mock_market_data)
    
    # 假设候选池为 000001
    candidates = ["000001"]
    
    # 因为 mock_market_data.get_market_cap 默认返回 50亿（< 100亿）
    # 日线数据中有涨停（最后一根 10.5 -> 11.55）
    # 当前价 > 涨停日最低价（现价 10.5 > 9.0）
    qualified = momentum.run(candidates, spot_df=sample_spot_df)
    
    assert "000001" in qualified
    assert momentum._stats["passed"] == 1
    assert momentum._stats["market_cap_fail"] == 0
    assert momentum._stats["bars_fail"] == 0