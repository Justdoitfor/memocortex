"""Hybrid Recall Router — 4 信号融合统一召回入口

流程:
  1. 用 query 向量化, 从 ChromaDB 召回 Top-(K × oversample) 候选 (cast a wider net)
  2. 对每个候选计算 4 信号
  3. 加权融合 → final_score
  4. 重排 → 截 Top-K
  5. 异步更新 last_recalled_at / recall_count
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger

from app.config import config
from app.models import (
    MemoryRecord,
    MemoryType,
    RecallResult,
    RecallSignals,
)
from app.recall.signals import (
    compute_graph_proximity,
    compute_importance,
    compute_temporal_decay,
    compute_vector_sim,
    fuse_signals,
)
from app.storage import get_kg, get_vector_store
from app.utils.metrics import metrics

# 召回候选数 = top_k × OVERSAMPLE, 大网捞了再重排, 提高最终质量
_OVERSAMPLE = 3


class HybridRecallRouter:
    """统一召回入口 — 业务方应只调用 search(), 不要直接访问 VectorStore."""

    def __init__(self) -> None:
        self._vector = get_vector_store()
        self._kg = get_kg()
        logger.info(
            f"HybridRecall 权重: vec={config.recall_w_vector} "
            f"temp={config.recall_w_temporal} graph={config.recall_w_graph} "
            f"imp={config.recall_w_importance}"
        )

    async def search(
        self,
        user_id: str,
        query: str,
        memory_types: list[MemoryType] | None = None,
        top_k: int | None = None,
        weights: tuple[float, float, float, float] | None = None,
    ) -> list[RecallResult]:
        """主入口."""
        top_k = top_k or config.default_top_k
        type_strs = [t.value for t in memory_types] if memory_types else None

        with metrics.timer("recall.total.latency"):
            # 1. 向量召回, 拉宽候选池
            candidates: list[tuple[MemoryRecord, float]] = await self._vector.search(
                user_id=user_id,
                query=query,
                memory_types=type_strs,
                top_k=top_k * _OVERSAMPLE,
            )

            if not candidates:
                return []

            # 2. 查询实体 + 用户邻居 (供 graph_proximity 信号用)
            query_entities = self._extract_query_entities(query)
            user_neighbors: set[str] = set()
            for ent in query_entities:
                user_neighbors |= await self._kg.neighbors(user_id, ent, max_hops=2)

            # 3. 算分 + 融合
            now = datetime.now()
            scored: list[RecallResult] = []
            for record, raw_sim in candidates:
                sig = RecallSignals(
                    vector_sim=compute_vector_sim(raw_sim),
                    temporal_decay=compute_temporal_decay(record.created_at, now=now),
                    graph_proximity=compute_graph_proximity(
                        record, query_entities, user_neighbors
                    ),
                    importance=compute_importance(record),
                )
                sig.final_score = fuse_signals(
                    sig.vector_sim,
                    sig.temporal_decay,
                    sig.graph_proximity,
                    sig.importance,
                    weights=weights,
                )
                scored.append(RecallResult(record=record, signals=sig))

            # 4. 重排 + 截断
            scored.sort(key=lambda r: r.signals.final_score, reverse=True)
            top = scored[:top_k]
            for i, r in enumerate(top, 1):
                r.rank = i

        # 5. 异步更新 last_recalled_at / recall_count (best effort, 不阻塞返回)
        try:
            for r in top:
                await self._vector.update_metadata(
                    r.record.id,
                    user_id,
                    {
                        "recall_count": r.record.recall_count + 1,
                        "last_recalled_at_iso": now.isoformat(),
                    },
                )
        except Exception as e:
            logger.debug(f"召回元数据更新失败 (非致命): {e}")

        metrics.incr("recall.invocations")
        return top

    @staticmethod
    def _extract_query_entities(query: str) -> set[str]:
        """从 query 中粗抽实体. MVP 用空格切分 + 去掉短词, 生产可换 NER."""
        words = {w.strip("，。！？,.!?;:") for w in query.split()}
        return {w for w in words if len(w) >= 2}


# 全局单例
recall_router = HybridRecallRouter()
