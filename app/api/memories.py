"""/v1/memories — 写入 / 召回 / 删除"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.models import (
    ForgetRequest,
    SearchRequest,
    SearchResponse,
    WriteRequest,
    WriteResponse,
)
from app.orchestrator import orchestrator

router = APIRouter()


@router.post("/memories", response_model=WriteResponse, summary="写入一条记忆")
async def write_memory(req: WriteRequest) -> WriteResponse:
    """统一写入入口. 按 req.type 路由到 5 类记忆之一."""
    try:
        return await orchestrator.write(req)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"写入失败: {e}",
        ) from e


@router.post("/memories/search", response_model=SearchResponse, summary="混合召回")
async def search_memories(req: SearchRequest) -> SearchResponse:
    """4 信号 Hybrid Recall: 向量 + 时间衰减 + 图扩展 + 重要度."""
    try:
        return await orchestrator.search(
            user_id=req.user_id,
            query=req.query,
            types=req.types,
            top_k=req.top_k,
            session_id=req.session_id,
            score_threshold=req.score_threshold,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"召回失败: {e}",
        ) from e


@router.post("/memories/forget", summary="删除记忆 (GDPR)")
async def forget_memory(req: ForgetRequest) -> dict:
    """按 memory_id 删除. all_user_data=True 时级联清空用户全量数据."""
    if not req.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="删除需要 confirm=True",
        )
    if not req.memory_id and not req.query:
        # 整个用户级删除
        return await orchestrator.forget(user_id=req.user_id, all_user_data=True)
    if req.memory_id:
        return await orchestrator.forget(user_id=req.user_id, memory_id=req.memory_id)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="按 query 模糊删除暂未实现 (MVP)",
    )
