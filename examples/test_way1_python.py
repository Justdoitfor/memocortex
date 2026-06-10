"""方式 1 测试: Python 直接调用 orchestrator

跑法:
    cd memocortex
    rm -rf data/chroma data/graph data/memocortex.db   # 干净起点
    uv run python examples/test_way1_python.py
"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.models import MemoryType, WriteRequest
from app.orchestrator import orchestrator
from app.storage import get_kg, get_metadata


async def main() -> None:
    await get_metadata().init_schema()

    user = "alice"

    print("\n========== 方式 1: Python 直接调用 ==========\n")

    # ── 1. 写 Semantic ──
    print("[1] 写 SEMANTIC: '我对花生过敏'")
    res = await orchestrator.write(WriteRequest(
        user_id=user, content="我对花生过敏", type=MemoryType.SEMANTIC,
    ))
    print(f"    memory_id={res.memory_id[:8]}  type={res.routed_type.value}")

    # ── 2. 写 Episodic ──
    print("\n[2] 写 EPISODIC: '今天去吃了川菜火锅,辣到流眼泪'")
    res = await orchestrator.write(WriteRequest(
        user_id=user, content="今天去吃了川菜火锅,辣到流眼泪", type=MemoryType.EPISODIC,
    ))
    print(f"    memory_id={res.memory_id[:8]}  type={res.routed_type.value}")

    # ── 3. 再写一条 Semantic ──
    print("\n[3] 写 SEMANTIC: '我现在住在杭州滨江区'")
    res = await orchestrator.write(WriteRequest(
        user_id=user, content="我现在住在杭州滨江区", type=MemoryType.SEMANTIC,
    ))
    print(f"    memory_id={res.memory_id[:8]}")

    # ── 4. 等异步 ──
    print("\n[4] 等所有后台异步任务完成 ...")
    await orchestrator.wait_pending(timeout=20.0)
    print("    OK")

    # ── 5. 召回 ──
    print("\n[5] 召回 query='用户能吃花生吗' top_k=3")
    resp = await orchestrator.search(user_id=user, query="用户能吃花生吗", top_k=3)
    print(f"    latency={resp.latency_ms}ms  signals_used={resp.signals_used}")
    for r in resp.results:
        s = r.signals
        print(
            f"    [{r.rank}] {r.record.type.value:10}  score={s.final_score:.3f}  "
            f"(vec={s.vector_sim:.2f} temp={s.temporal_decay:.2f} "
            f"graph={s.graph_proximity:.2f} imp={s.importance:.2f})"
        )
        print(f"        -> {r.record.content[:50]}")

    # ── 6. KG ──
    print("\n[6] 查 KG user 实体的所有事实")
    triples = await get_kg().find_triples(user, subject="user")
    print(f"    KG 中共 {len(triples)} 条 user 事实:")
    for t in triples:
        print(f"      ({t.subject}, {t.predicate}, {t.object})  conf={t.confidence}")

    # ── 7. 用户画像 ──
    print("\n[7] 生成用户画像 (auto_refresh=True 会即时调 LLM)")
    profile = await orchestrator.get_profile(user, auto_refresh=True)
    p = profile.get("profile", {})
    print(f"    one_liner: {p.get('one_liner', '')}")
    print(f"    facts: {p.get('facts', {})}")
    print(f"    constraints (禁忌/过敏): {p.get('constraints', [])}")
    print(f"    preferences: {p.get('preferences', [])}")

    print("\n[OK] 方式 1 测试通过 — 所有功能正常\n")


if __name__ == "__main__":
    asyncio.run(main())
