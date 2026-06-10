"""/admin — 反思手动触发 / 仲裁日志查询 / Eval 入口"""

from __future__ import annotations

from fastapi import APIRouter

from app.reflection import run_all_for_user
from app.storage import get_metadata

router = APIRouter()


@router.post("/reflect/{user_id}", summary="手动触发用户的全部反思任务")
async def trigger_reflection(user_id: str) -> dict:
    return await run_all_for_user(user_id)


@router.get("/arbitrations/{user_id}", summary="查询冲突仲裁审计日志")
async def list_arbitrations(user_id: str, limit: int = 50) -> dict:
    meta = get_metadata()
    items = await meta.list_arbitrations(user_id, limit=limit)
    return {"user_id": user_id, "count": len(items), "items": items}


@router.get("/eval/last/{suite}", summary="查询某 suite 的上次 eval 跑分")
async def get_last_eval(suite: str) -> dict:
    meta = get_metadata()
    last = await meta.last_eval(suite)
    return last or {"suite": suite, "score": None, "message": "无历史 eval 记录"}
