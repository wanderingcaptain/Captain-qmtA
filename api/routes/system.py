from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio

from core.engine_manager import manager
from utils.log_capture import ws_log_handler

router = APIRouter()

@router.get("/status")
def get_status():
    return manager.get_status()

@router.post("/intraday/start")
def start_intraday():
    manager.start_intraday()
    return {"status": "success", "message": "Intraday engine started"}

@router.post("/intraday/stop")
def stop_intraday():
    manager.stop_intraday()
    return {"status": "success", "message": "Intraday engine stopped"}

@router.post("/screening/start")
def start_screening():
    manager.start_nightly_screening()
    return {"status": "success", "message": "Nightly screening started in background"}

@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """通过 WebSocket 将捕获的 Python 日志推送到前端"""
    await websocket.accept()
    
    # 推送历史日志
    for log_item in ws_log_handler.history:
        await websocket.send_json(log_item)
        
    # 订阅新日志
    q = ws_log_handler.subscribe()
    try:
        while True:
            # 阻塞等待新日志，并推送
            log_item = await q.get()
            await websocket.send_json(log_item)
    except WebSocketDisconnect:
        pass
    finally:
        ws_log_handler.unsubscribe(q)
