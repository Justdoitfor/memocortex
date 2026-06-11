"""/v1/memories — 写入 / 召回 / 删除

对外暴露 5 类长期记忆: EPISODIC / SEMANTIC / PROCEDURAL / REFLECTIVE / IMPLICIT.
其中 REFLECTIVE 和 IMPLICIT 由后台 Worker 自动生成, 不接受直接写入.
WORKING (短期会话上下文) 完全不暴露 — 应由上游 Agent 框架 (LangGraph state /
Redis) 自己管理. 我们的产品定位是 *长期* 记忆中间件.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.models import (
    ForgetRequest,
    MemoryType,
    SearchRequest,
    SearchResponse,
    WriteRequest,
    WriteResponse,
)
from app.orchestrator import orchestrator

router = APIRouter()

# 对外公开的 5 类长期记忆
_PUBLIC_TYPES = {MemoryType.EPISODIC, MemoryType.SEMANTIC,
                 MemoryType.PROCEDURAL, MemoryType.REFLECTIVE, MemoryType.IMPLICIT}

# 仅 3 类支持手动写入, 其余 2 类由后台 Worker 生成
_WRITEABLE_TYPES = {MemoryType.EPISODIC, MemoryType.SEMANTIC, MemoryType.PROCEDURAL}


def _guard_public_type(t: MemoryType) -> None:
    """API 入口拒绝内部专用类型 (WORKING)."""
    if t not in _PUBLIC_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"type='{t.value}' 不对外暴露. MemoCortex 定位是长期记忆中间件, "
                "短期会话上下文请用 LangGraph state 或 Redis 自行管理. "
                "对外支持: episodic / semantic / procedural / reflective / implicit"
            ),
        )


@router.post("/memories", response_model=WriteResponse, summary="写入一条记忆")
async def write_memory(req: WriteRequest) -> WriteResponse:
    """统一写入入口. 按 req.type 路由.

    - episodic (默认): 时序事件, 会异步触发 semantic 抽取
    - semantic: 同步走 LLM 抽取三元组 + 冲突仲裁 + Staleness 软废弃
    - procedural: 任务模板, 需要 structured.steps
    - reflective: ❌ 由 Reflection Worker 从 Semantic 聚合, 不接受直接写
    - implicit: ❌ 由 Pattern Miner 从行为信号挖掘, 不接受直接写
    """
    _guard_public_type(req.type)
    if req.type not in _WRITEABLE_TYPES:
        if req.type == MemoryType.REFLECTIVE:
            hint = "用 POST /admin/reflect/{user_id} 手动触发刷新"
        else:  # IMPLICIT
            hint = "用 POST /admin/mine_patterns/{user_id} 手动触发挖掘 (Phase 2 上线)"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{req.type.value} 记忆由后台 Worker 自动生成, 不接受直接写入. {hint}",
        )
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
    if req.types:
        for t in req.types:
            _guard_public_type(t)
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
