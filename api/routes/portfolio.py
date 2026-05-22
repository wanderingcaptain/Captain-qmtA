from fastapi import APIRouter
from core.engine_manager import manager

router = APIRouter()

@router.get("/summary")
def get_portfolio_summary():
    """获取资产概览"""
    try:
        # 获取当前市场现价用于盯市计算
        codes = list(manager.portfolio.positions.keys())
        current_prices = {}
        if codes:
            spot_df = manager.md.get_spot()
            for code in codes:
                row = spot_df[spot_df["code"] == code]
                if not row.empty:
                    current_prices[code] = float(row.iloc[0]["price"])
        
        return {
            "status": "success",
            "data": {
                "total_assets": manager.portfolio.total_assets(current_prices),
                "cash": manager.portfolio.cash,
                "positions_value": manager.portfolio.total_positions_value(current_prices),
                "consecutive_loss_days": manager.portfolio.get_consecutive_loss_days()
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/positions")
def get_positions():
    """获取所有持仓明细"""
    try:
        codes = list(manager.portfolio.positions.keys())
        current_prices = {}
        if codes:
            spot_df = manager.md.get_spot()
            for code in codes:
                row = spot_df[spot_df["code"] == code]
                if not row.empty:
                    current_prices[code] = float(row.iloc[0]["price"])

        pos_list = []
        for code, pos in manager.portfolio.positions.items():
            cp = current_prices.get(code, pos.entry_price)
            unrealized = (cp - pos.entry_price) * pos.remaining_quantity
            pct_chg = ((cp - pos.entry_price) / pos.entry_price) * 100 if pos.entry_price > 0 else 0
            
            p_dict = pos.to_dict()
            p_dict["current_price"] = cp
            p_dict["unrealized_pnl"] = unrealized
            p_dict["unrealized_pct"] = pct_chg
            pos_list.append(p_dict)
            
        return {"status": "success", "data": pos_list}
    except Exception as e:
        return {"status": "error", "message": str(e)}
