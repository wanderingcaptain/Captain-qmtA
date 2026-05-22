"""
FastAPI 后端主入口。
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from api.routes import system, market, portfolio, config
from utils.log_capture import attach_to_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时注入日志捕获器
    attach_to_logger()
    yield
    # 停止时可以进行清理（目前不需要）

app = FastAPI(title="Captain QMT_THS API", lifespan=lifespan)

# CORS 配置（针对本地开发分离端口时）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(system.router, prefix="/api/system", tags=["System"])
app.include_router(market.router, prefix="/api/market", tags=["Market"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(config.router, prefix="/api/config", tags=["Config"])

# 挂载前端静态文件（如果存在）
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")

if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    @app.get("/")
    def index():
        return {"message": "Captain QMT_THS API is running. Frontend build not found in frontend/dist/"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
