"""/health + /metrics"""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.config import config
from app.utils.metrics import metrics

router = APIRouter()


@router.get("/health", summary="健康检查")
async def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "data_dir": str(config.data_dir.resolve()),
    }


@router.get("/metrics", summary="进程指标 (简化 JSON, 不是 Prometheus 格式)")
async def get_metrics() -> dict:
    return metrics.snapshot()
