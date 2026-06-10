"""Memory Orchestrator — 统一的 read/write/search/forget 入口

设计:
  - 不用 LangGraph 重型编排 (MVP 流程比较直接, LangGraph 反而过度抽象)
  - 暴露 4 个清晰的 async 入口供 API/SDK/MCP 共享调用
  - 路由策略 in-place: 业务方传 type 则按 type 路由, 否则智能推断
  - 所有调用走 metrics.timer 采集延迟
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from loguru import logger

# 强制触发 arbitrator 模块 init, 把 ConflictArbitrator 注入 SemanticMemory
import app.arbitrator  # noqa: F401
from app.memories import (
    episodic_memory,
    procedural_memory,
    reflective_memory,
    semantic_memory,
    working_memory,
)
from app.models import (
    MemoryRecord,
    MemoryType,
    RecallResult,
    SearchResponse,
    WriteRequest,
    WriteResponse,
)
from app.recall import recall_router
from app.storage import get_metadata, get_vector_store
from app.utils.metrics import metrics


class MemoryOrchestrator:
    """4 入口聚合器: write / search / get_profile / forget."""

    def __init__(self) -> None:
        self._meta = get_metadata()
        self._vector = get_vector_store()
        # 持有 background tasks 引用, 防止被 GC 提前回收 (Python 3.11+ 已知问题)
        self._bg_tasks: set = set()
        logger.info("MemoryOrchestrator 初始化完成")

    def _spawn_bg(self, coro) -> None:
        """fire-and-forget 启动后台任务, 同时持有引用避免 GC 提前回收."""
        import asyncio

        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def wait_pending(self, timeout: float = 30.0) -> None:
        """等待所有未完成的 background tasks. eval / test 场景需要确定性."""
        import asyncio

        if not self._bg_tasks:
            return
        pending = list(self._bg_tasks)
        try:
            await asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True), timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"wait_pending 超时, 还有 {len(self._bg_tasks)} 个任务未完成")

    # ────────────────────────────────────────────────────────────────────
    # write — 路由 + 写入 + (可选) semantic 抽取
    # ────────────────────────────────────────────────────────────────────
    async def write(self, req: WriteRequest) -> WriteResponse:
        """统一写入入口.

        路由规则:
          - type=WORKING    → WorkingMemory (session 强相关)
          - type=PROCEDURAL → ProceduralMemory (需要 structured.steps)
          - type=SEMANTIC   → 直接 SemanticMemory.write_from_text
          - type=EPISODIC (默认) →
              * 写 Episodic
              * 异步触发 semantic 抽取 (best effort, 不阻塞返回)
        """
        record = MemoryRecord(
            user_id=req.user_id,
            session_id=req.session_id,
            type=req.type,
            content=req.content,
            structured=req.structured or {},
            importance=req.importance if req.importance is not None else 0.5,
            tags=req.tags,
        )

        arbitration = None

        if req.type == MemoryType.WORKING:
            memory_id = await working_memory.write(record)

        elif req.type == MemoryType.PROCEDURAL:
            steps = req.structured.get("steps", [])
            task = req.structured.get("task_pattern", req.content)
            memory_id = await procedural_memory.write(
                user_id=req.user_id,
                task_pattern=task,
                steps=steps,
                success_rate=req.structured.get("success_rate", 1.0),
                tags=req.tags,
            )

        elif req.type == MemoryType.SEMANTIC:
            # 走 SemanticMemory.write_from_text (LLM 抽取 + 冲突仲裁)
            results = await semantic_memory.write_from_text(
                user_id=req.user_id,
                text=req.content,
                source_memory_id=record.id,
            )
            memory_id = record.id
            # 取第一个 arbitration 给上层 (如果有)
            for r in results:
                if r.get("arbitration"):
                    arbitration = r["arbitration"]
                    break

        else:  # EPISODIC (默认)
            memory_id = await episodic_memory.write(record)
            # 异步触发 semantic 抽取 — 用 _spawn_bg 持有引用避免 GC
            self._spawn_bg(
                self._extract_semantic_safely(req.user_id, req.content, record.id)
            )

        metrics.incr(f"orchestrator.write.{req.type.value}")
        return WriteResponse(
            memory_id=memory_id, routed_type=req.type, arbitration=arbitration
        )

    async def _extract_semantic_safely(
        self, user_id: str, text: str, source_memory_id: str
    ) -> None:
        """异步从 episodic 内容抽取 semantic facts, 失败仅 warning."""
        try:
            await semantic_memory.write_from_text(
                user_id=user_id, text=text, source_memory_id=source_memory_id
            )
        except Exception as e:
            logger.warning(f"后台 semantic 抽取失败: {e}")

    # ────────────────────────────────────────────────────────────────────
    # search — Hybrid Recall + Working 兜底 + Profile 注入
    # ────────────────────────────────────────────────────────────────────
    async def search(
        self,
        user_id: str,
        query: str,
        types: list[MemoryType] | None = None,
        top_k: int | None = None,
        session_id: str | None = None,
    ) -> SearchResponse:
        """统一召回入口. 返回 RecallResult 列表 + 性能数据."""
        start = time.perf_counter()

        results: list[RecallResult] = await recall_router.search(
            user_id=user_id,
            query=query,
            memory_types=types,
            top_k=top_k,
        )

        # 如果 session_id 给了, 把 Working Memory 最近几条作为最高优先级前置
        if session_id and (types is None or MemoryType.WORKING in types):
            working = await working_memory.read(user_id, session_id, limit=3)
            # working 直接给满分前置, 不混入向量分数
            working_results = [
                RecallResult(
                    record=w,
                    signals=__import__(
                        "app.models", fromlist=["RecallSignals"]
                    ).RecallSignals(final_score=1.0),
                    rank=0,
                )
                for w in working
            ]
            results = working_results + [r for r in results if r.record.type != MemoryType.WORKING]
            # 重排 rank
            for i, r in enumerate(results, 1):
                r.rank = i

        latency_ms = (time.perf_counter() - start) * 1000
        return SearchResponse(
            results=results,
            latency_ms=round(latency_ms, 2),
            signals_used=["vector", "temporal", "graph", "importance"],
        )

    # ────────────────────────────────────────────────────────────────────
    # get_profile — 直接读 Reflective Memory
    # ────────────────────────────────────────────────────────────────────
    async def get_profile(self, user_id: str, auto_refresh: bool = False) -> dict[str, Any]:
        """获取用户画像. auto_refresh=True 时若无缓存则触发实时生成."""
        cached = await reflective_memory.get(user_id)
        if cached:
            return cached
        if auto_refresh:
            profile = await reflective_memory.refresh(user_id)
            return {"profile": profile, "updated_at": datetime.now().isoformat()}
        return {"profile": {}, "updated_at": None}

    # ────────────────────────────────────────────────────────────────────
    # forget — GDPR Right to be Forgotten
    # ────────────────────────────────────────────────────────────────────
    async def forget(
        self,
        user_id: str,
        memory_id: str | None = None,
        all_user_data: bool = False,
    ) -> dict[str, Any]:
        """按 memory_id 或全量删除."""
        if all_user_data:
            from app.storage import get_kg, get_vector_store
            vec_deleted = await get_vector_store().delete_by_user(user_id)
            kg_deleted = await get_kg().delete_by_user(user_id)
            # SQLite: 暴力删除该用户所有 memory + profile
            records = await self._meta.list_memories(user_id, limit=100000)
            meta_deleted = 0
            for r in records:
                if await self._meta.delete_memory(r.id):
                    meta_deleted += 1
            logger.warning(
                f"GDPR forget: user={user_id} vec={vec_deleted} kg={kg_deleted} meta={meta_deleted}"
            )
            return {
                "user_id": user_id,
                "vector_deleted": vec_deleted,
                "graph_deleted": kg_deleted,
                "metadata_deleted": meta_deleted,
            }

        if memory_id:
            ok_vec = await self._vector.delete(memory_id, user_id)
            ok_meta = await self._meta.delete_memory(memory_id)
            return {"memory_id": memory_id, "deleted": ok_vec and ok_meta}

        return {"error": "需要 memory_id 或 all_user_data=True"}


# 全局单例
orchestrator = MemoryOrchestrator()
