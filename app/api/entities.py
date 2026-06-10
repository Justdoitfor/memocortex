"""/v1/users/{id}/entities/{name} — 直接查 KG"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.storage import get_kg

router = APIRouter()


@router.get("/users/{user_id}/entities/{entity}", summary="查实体的所有三元组")
async def get_entity(
    user_id: str,
    entity: str,
    predicate: str | None = Query(default=None),
) -> dict:
    """查 user.{predicate} 或所有 user.* 事实."""
    kg = get_kg()
    triples = await kg.find_triples(user_id, subject=entity, predicate=predicate)
    neighbors = await kg.neighbors(user_id, entity, max_hops=2)
    return {
        "user_id": user_id,
        "entity": entity,
        "triples": [t.model_dump(mode="json") for t in triples],
        "neighbors": sorted(neighbors),
    }
