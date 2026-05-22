from fastapi import APIRouter
from core.engine_manager import manager
from data.market_data import MarketData

router = APIRouter()

@router.get("/sentiment")
def get_market_sentiment():
    """获取大盘涨跌家数"""
    try:
        adv, dec, flat = manager.md.get_market_advancing_declining()
        return {
            "status": "success",
            "data": {
                "advancing": adv,
                "declining": dec,
                "flat": flat
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/watchlist")
def get_watchlist():
    """获取核心监控池内容及简要现价信息"""
    codes = manager.engine.watchlist
    if not codes:
        return {"status": "success", "data": []}
    
    try:
        spot_df = manager.md.get_spot()
        pool_data = []
        for code in codes:
            row = spot_df[spot_df["code"] == code]
            if not row.empty:
                pool_data.append({
                    "code": code,
                    "name": row.iloc[0]["name"],
                    "price": float(row.iloc[0]["price"]),
                    "pct_chg": float(row.iloc[0]["pct_chg"])
                })
            else:
                pool_data.append({"code": code, "name": "未知", "price": 0.0, "pct_chg": 0.0})
                
        return {"status": "success", "data": pool_data}
    except Exception as e:
        return {"status": "error", "message": str(e)}
