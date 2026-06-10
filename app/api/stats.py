"""/v1/stats — 给前端 Playground 用的实时记忆看板"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.memories.working import working_memory
from app.models import MemoryType
from app.storage import get_kg, get_metadata

router = APIRouter()


class _MemoryItem(BaseModel):
    id: str
    content: str
    type: str
    importance: float
    created_at: str
    tier: str


class _TripleItem(BaseModel):
    subject: str
    predicate: str
    object: str


class UserStatsResponse(BaseModel):
    user_id: str
    counts: dict[str, int]  # 5 类记忆各多少条
    recent: dict[str, list[_MemoryItem]]  # 5 类各前 N 条
    triples: list[_TripleItem]  # KG 全部 user 事实
    profile: dict[str, Any] | None
    arbitration_count: int


@router.get(
    "/stats/{user_id}",
    response_model=UserStatsResponse,
    summary="一次拉取该用户的 5 类记忆 + KG + 画像 + 审计计数",
)
async def get_user_stats(user_id: str, recent_n: int = 5) -> UserStatsResponse:
    meta = get_metadata()
    kg = get_kg()

    counts: dict[str, int] = {}
    recent: dict[str, list[_MemoryItem]] = {}

    # Working / Episodic / Semantic / Procedural — 走 list_memories
    for mtype in [MemoryType.WORKING, MemoryType.EPISODIC,
                  MemoryType.SEMANTIC, MemoryType.PROCEDURAL]:
        items = await meta.list_memories(user_id, memory_type=mtype.value, limit=100)
        counts[mtype.value] = len(items)
        recent[mtype.value] = [
            _MemoryItem(
                id=r.id,
                content=r.content[:300],
                type=r.type.value,
                importance=r.importance,
                created_at=r.created_at.isoformat(),
                tier=r.tier,
            )
            for r in items[:recent_n]
        ]

    # Working 优先走内存 LRU (更新鲜)
    try:
        in_mem = await working_memory.read(user_id, session_id=None, limit=recent_n)
        if in_mem:
            recent[MemoryType.WORKING.value] = [
                _MemoryItem(
                    id=r.id,
                    content=r.content[:300],
                    type=r.type.value,
                    importance=r.importance,
                    created_at=r.created_at.isoformat(),
                    tier=r.tier,
                )
                for r in in_mem
            ]
    except Exception:
        pass

    # Reflective — 单独的 profile blob
    profile = await meta.get_profile(user_id)
    counts[MemoryType.REFLECTIVE.value] = 1 if profile else 0

    # KG triples
    triples = await kg.find_triples(user_id, subject="user")
    triple_items = [
        _TripleItem(subject=t.subject, predicate=t.predicate, object=t.object)
        for t in triples
    ]

    # 仲裁次数
    arbs = await meta.list_arbitrations(user_id, limit=1000)

    return UserStatsResponse(
        user_id=user_id,
        counts=counts,
        recent=recent,
        triples=triple_items,
        profile=profile,
        arbitration_count=len(arbs),
    )
