"""FastAPI 应用入口 — 路由挂载 + lifespan 初始化"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app import __version__
from app.api import admin, demo, entities, health, memories, profile, signals, stats
from app.config import config
from app.reflection import start_scheduler, stop_scheduler
from app.storage import get_kg, get_metadata
from app.utils.logger import setup_logger


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logger()
    logger.info("=" * 60)
    logger.info(f"MemoCortex v{__version__} 启动")
    logger.info(f"监听: http://{config.host}:{config.port}")
    logger.info(f"数据目录: {config.data_dir.resolve()}")
    logger.info("=" * 60)

    # 初始化存储 schema
    config.ensure_dirs()
    await get_metadata().init_schema()

    # 启动反思调度器
    start_scheduler()

    yield

    # 优雅关闭: 持久化图 + 停调度器
    logger.info("正在关闭 MemoCortex...")
    try:
        await get_kg().persist()
    except Exception as e:
        logger.warning(f"持久化图失败: {e}")
    stop_scheduler()
    logger.info("MemoCortex 已停止")


app = FastAPI(
    title="MemoCortex",
    version=__version__,
    description="Agent 长期记忆中间件 — 5 类分层记忆 / 4 信号 Hybrid Recall / LLM-as-Arbitrator",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由挂载
app.include_router(health.router, tags=["健康检查"])
app.include_router(memories.router, prefix="/v1", tags=["Memories"])
app.include_router(profile.router, prefix="/v1", tags=["Profile"])
app.include_router(entities.router, prefix="/v1", tags=["Entities"])
app.include_router(stats.router, prefix="/v1", tags=["Stats"])
app.include_router(demo.router, prefix="/v1", tags=["Demo"])
app.include_router(signals.router, prefix="/v1", tags=["Signals (Phase 2)"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])


@app.get("/")
async def root():
    return {
        "name": "MemoCortex",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.api.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_level=config.log_level.lower(),
    )
