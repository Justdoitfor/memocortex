"""/v1/users/{id}/profile — Reflective Memory 入口"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.orchestrator import orchestrator

router = APIRouter()


@router.get("/users/{user_id}/profile", summary="获取用户画像")
async def get_profile(
    user_id: str,
    auto_refresh: bool = Query(default=False, description="若无缓存则即时生成"),
) -> dict:
    return await orchestrator.get_profile(user_id, auto_refresh=auto_refresh)
