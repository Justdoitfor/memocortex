"""/v1/signals — 行为信号收集 + Pattern 挖掘触发"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.models import SignalType
from app.pattern import mine_patterns_for_user, track_signal
from app.storage import get_metadata

router = APIRouter()


class TrackSignalRequest(BaseModel):
    user_id: str
    signal_type: SignalType
    context_tags: list[str] = Field(default_factory=list)
    memory_ids_in_context: list[str] = Field(default_factory=list)
    session_id: str | None = None
    extra: dict = Field(default_factory=dict)


class TrackSignalResponse(BaseModel):
    signal_id: int
    status: str = "recorded"


@router.post(
    "/signals/track",
    response_model=TrackSignalResponse,
    summary="上报一条用户行为信号 (Pattern Miner 后台挖掘用)",
)
async def post_signal(req: TrackSignalRequest) -> TrackSignalResponse:
    sid = await track_signal(
        user_id=req.user_id,
        signal_type=req.signal_type,
        context_tags=req.context_tags,
        memory_ids_in_context=req.memory_ids_in_context,
        session_id=req.session_id,
        extra=req.extra,
    )
    if sid < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="非法 signal_type",
        )
    return TrackSignalResponse(signal_id=sid)


@router.get("/signals/{user_id}", summary="查询用户最近行为信号 (调试 / 审计)")
async def list_signals(
    user_id: str,
    signal_type: str | None = None,
    limit: int = 50,
) -> dict:
    meta = get_metadata()
    items = await meta.list_signals(user_id, signal_type=signal_type, limit=limit)
    return {"user_id": user_id, "count": len(items), "items": items}
