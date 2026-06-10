"""MemoCortex 基础 Demo — 30 行展示 5 类记忆 + Hybrid Recall

无需 LLM API key 即可跑通 (semantic 抽取/冲突仲裁需 LLM, 这里仅演示主链路).

用法:
    uv run python examples/demo_basic.py
"""

from __future__ import annotations

import asyncio
import sys

# Windows 终端 GBK 编码兜底: 强制 stdout 用 UTF-8 (不影响其他平台)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.models import MemoryType, SearchRequest, WriteRequest
from app.orchestrator import orchestrator
from app.storage import get_metadata
from app.utils.logger import setup_logger


async def main() -> None:
    setup_logger()
    await get_metadata().init_schema()

    USER = "alice"
    SESSION = "demo_session_1"

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  MemoCortex Basic Demo — 5 类记忆 / 4 信号 Hybrid Recall")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    # ── 1. 写 5 条 Episodic ──
    print("【Episodic】 写入 5 条日常事件")
    for content in [
        "今天和朋友去吃了川菜火锅, 麻辣的我吃得很爽",
        "下午去图书馆读了一本心理学的书",
        "晚上慢跑了 5 公里",
        "工作上完成了 RAG 模块的优化, 召回率提升了 15%",
        "看了一部关于量子物理的纪录片",
    ]:
        res = await orchestrator.write(
            WriteRequest(user_id=USER, session_id=SESSION, content=content)
        )
        print(f"  + {content[:34]:34}  → id={res.memory_id[:8]}")

    # ── 2. 写 1 条 Procedural ──
    print("\n【Procedural】 注册一个任务模板")
    proc_res = await orchestrator.write(
        WriteRequest(
            user_id=USER,
            content="如何排查数据库慢查询",
            type=MemoryType.PROCEDURAL,
            structured={
                "task_pattern": "数据库慢查询排查",
                "steps": [
                    "用 EXPLAIN 看执行计划",
                    "检查索引覆盖情况",
                    "评估是否要加联合索引或重写 SQL",
                ],
            },
        )
    )
    print(f"  + 数据库慢查询排查 模板  → id={proc_res.memory_id[:8]}")

    # ── 3. 写 3 条 Working ──
    print("\n【Working】 当前会话上下文 (前面说过的话)")
    for s in ["这是会话第 1 句", "这是会话第 2 句", "这是会话第 3 句"]:
        await orchestrator.write(
            WriteRequest(
                user_id=USER, session_id=SESSION, content=s, type=MemoryType.WORKING
            )
        )
        print(f"  + {s}")

    # ── 4. Hybrid Recall 演示 ──
    print("\n【Hybrid Recall】 4 信号融合召回 (不含 working, 展示纯向量+时间+图+重要度融合效果)")
    for query in ["运动相关", "技术工作", "学习相关"]:
        resp = await orchestrator.search(
            user_id=USER, query=query, top_k=3
            # 注意: 不传 session_id, 这样 Working Memory 不会强前置
        )
        print(f"\n  Q: \"{query}\"   (latency={resp.latency_ms:.0f}ms)")
        for r in resp.results:
            sig = r.signals
            print(
                f"    [{r.rank}] {r.record.type.value:11} "
                f"score={sig.final_score:.3f}  "
                f"(vec={sig.vector_sim:.2f} temp={sig.temporal_decay:.2f} "
                f"graph={sig.graph_proximity:.2f} imp={sig.importance:.2f})  "
                f"-> {r.record.content[:38]}"
            )

    # ── 5. Metrics ──
    print("\n【Metrics】 进程指标快照")
    from app.utils.metrics import metrics

    snap = metrics.snapshot()
    print(f"  写入: {snap['counters']}")
    if "recall.total.latency" in snap.get("histograms", {}):
        h = snap["histograms"]["recall.total.latency"]
        print(f"  召回延迟: P50={h['p50_ms']:.1f}ms  P95={h['p95_ms']:.1f}ms  N={h['count']}")

    print("\n[OK] Demo 跑完. 数据已落盘到 ./data/. 再次运行会继续累积.\n")


if __name__ == "__main__":
    asyncio.run(main())
