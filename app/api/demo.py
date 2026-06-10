"""/v1/demo — 给前端 Demo 用的一键聚合接口

一次请求, 返回完整冲突仲裁演示数据 (写入 → 仲裁 → 召回 → KG + 审计).
前端拿到这个 payload 就能直接放动画, 无需多次请求拼装.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.memories.semantic import semantic_memory
from app.models import MemoryType, WriteRequest
from app.orchestrator import orchestrator
from app.storage import get_kg, get_metadata

router = APIRouter()


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                       预设场景                                       ║
# ╚══════════════════════════════════════════════════════════════════════╝


SCENARIOS: dict[str, dict[str, Any]] = {
    "relocation": {
        "title": "用户搬家 — 应触发 REPLACE",
        "subtitle": "lives_in 是 unique 字段, 旧地址被新地址完全取代",
        "writes": [
            "我现在住在北京朝阳区",
            "我搬家了, 现在住在上海浦东",
        ],
        "query": "用户现在住在哪里",
        "expected_action": "replace",
    },
    "allergy_merge": {
        "title": "过敏原合并 — 应触发 MERGE",
        "subtitle": "allergic_to 是 list 字段, 多个过敏原应当并存",
        "writes": [
            "我对花生过敏",
            "其实我对芝麻也过敏",
            "对了, 海鲜也不能吃, 也过敏",
        ],
        "query": "用户的过敏原有哪些",
        "expected_action": "merge",
    },
    "job_change": {
        "title": "跳槽换工作 — 应触发 REPLACE",
        "subtitle": "works_at 和 occupation 都是 unique, 整组事实被新工作替换",
        "writes": [
            "我目前在腾讯做后端开发",
            "我跳槽了, 现在在字节跳动做 AI 工程师",
        ],
        "query": "用户目前的工作",
        "expected_action": "replace",
    },
    "phone_upgrade": {
        "title": "换手机 — 应触发 REPLACE",
        "subtitle": "owns_phone 是 unique, 旧手机被新手机替代, 旧 Episodic 自动降权",
        "writes": [
            "我手机是 iPhone 14",
            "我换手机了, 现在用 iPhone 16 Pro",
        ],
        "query": "用户当前用什么手机",
        "expected_action": "replace",
    },
}


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                       Request / Response                             ║
# ╚══════════════════════════════════════════════════════════════════════╝


class ConflictScenarioRequest(BaseModel):
    scenario: str  # SCENARIOS 的 key


class _WriteStep(BaseModel):
    index: int
    content: str
    memory_id: str
    arbitration_action: str | None = None
    arbitration_reasoning: str | None = None


class _TripleOut(BaseModel):
    subject: str
    predicate: str
    object: str
    confidence: float


class _ArbitrationOut(BaseModel):
    subject: str
    predicate: str
    old_value: str | None
    new_value: str
    action: str
    reasoning: str
    confidence: float


class _RecallOut(BaseModel):
    rank: int
    content: str
    memory_type: str
    final_score: float
    vector_sim: float
    temporal_decay: float
    graph_proximity: float
    importance: float


class ConflictScenarioResponse(BaseModel):
    scenario: str
    title: str
    subtitle: str
    expected_action: str
    user_id: str

    # 时间轴: 每条写入 + 后续效果
    steps: list[_WriteStep]

    # 最终状态
    final_triples: list[_TripleOut]
    final_recall: list[_RecallOut]
    arbitrations: list[_ArbitrationOut]


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                       Endpoints                                      ║
# ╚══════════════════════════════════════════════════════════════════════╝


@router.get("/demo/scenarios", summary="列出所有预设场景")
async def list_scenarios() -> dict[str, Any]:
    return {
        "scenarios": [
            {
                "key": key,
                "title": s["title"],
                "subtitle": s["subtitle"],
                "expected_action": s["expected_action"],
                "writes_count": len(s["writes"]),
            }
            for key, s in SCENARIOS.items()
        ]
    }


@router.post(
    "/demo/conflict-scenario",
    response_model=ConflictScenarioResponse,
    summary="一键跑预设冲突场景, 返回完整动画数据",
)
async def run_conflict_scenario(req: ConflictScenarioRequest) -> ConflictScenarioResponse:
    if req.scenario not in SCENARIOS:
        raise HTTPException(404, f"scenario={req.scenario} 不存在, 可选: {list(SCENARIOS)}")

    sc = SCENARIOS[req.scenario]
    # 每个 demo 用独立 user_id, 隔离场景, 不污染真实用户数据
    demo_user = f"demo_{req.scenario}"

    # 1. 清空隔离
    try:
        await orchestrator.forget(user_id=demo_user, all_user_data=True)
    except Exception:
        pass

    # 2. 按序写入 (走 SEMANTIC 路径, 同步看到 arbitration)
    steps: list[_WriteStep] = []
    for i, content in enumerate(sc["writes"]):
        res = await orchestrator.write(
            WriteRequest(user_id=demo_user, content=content, type=MemoryType.SEMANTIC)
        )
        arb = res.arbitration
        steps.append(
            _WriteStep(
                index=i,
                content=content,
                memory_id=res.memory_id,
                arbitration_action=arb.action.value if arb else None,
                arbitration_reasoning=arb.reasoning if arb else None,
            )
        )

    # 等异步任务 (实际 SEMANTIC 路径同步, 但兜底)
    await orchestrator.wait_pending(timeout=15.0)

    # 3. 最终 KG 状态
    triples = await get_kg().find_triples(demo_user, subject="user")
    final_triples = [
        _TripleOut(
            subject=t.subject, predicate=t.predicate, object=t.object,
            confidence=t.confidence,
        )
        for t in triples
    ]

    # 4. 最终召回
    resp = await orchestrator.search(user_id=demo_user, query=sc["query"], top_k=5)
    final_recall = [
        _RecallOut(
            rank=r.rank,
            content=r.record.content,
            memory_type=r.record.type.value,
            final_score=round(r.signals.final_score, 4),
            vector_sim=round(r.signals.vector_sim, 4),
            temporal_decay=round(r.signals.temporal_decay, 4),
            graph_proximity=round(r.signals.graph_proximity, 4),
            importance=round(r.signals.importance, 4),
        )
        for r in resp.results
    ]

    # 5. 仲裁审计记录
    arb_items = await get_metadata().list_arbitrations(demo_user, limit=20)
    arbitrations = [
        _ArbitrationOut(
            subject=a["subject"],
            predicate=a["predicate"],
            old_value=a.get("old_value"),
            new_value=a["new_value"],
            action=a["action"],
            reasoning=a["reasoning"],
            confidence=a["confidence"],
        )
        for a in arb_items
    ]

    return ConflictScenarioResponse(
        scenario=req.scenario,
        title=sc["title"],
        subtitle=sc["subtitle"],
        expected_action=sc["expected_action"],
        user_id=demo_user,
        steps=steps,
        final_triples=final_triples,
        final_recall=final_recall,
        arbitrations=arbitrations,
    )
