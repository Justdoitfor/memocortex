"""Eval 指标计算 — Recall@K / Precision@K / MRR

不依赖 LLM, 纯算术 — 适合在 CI 中跑.
"""

from __future__ import annotations


def _is_match(retrieved_text: str, target_keyword: str) -> bool:
    """字面匹配 — 检索文本里是否含 target 关键词 (不区分大小写)."""
    return target_keyword.lower() in retrieved_text.lower()


def recall_at_k(retrieved: list[str], relevant: list[str], k: int | None = None) -> float:
    """Recall@K — relevant 中有多少被 retrieved (前 K 条) 命中.

    relevant: 期望被召回的关键词列表 (任意一条 retrieved 包含即算命中)
    """
    if not relevant:
        return 1.0
    pool = retrieved[:k] if k else retrieved
    hit = 0
    for tgt in relevant:
        if any(_is_match(r, tgt) for r in pool):
            hit += 1
    return hit / len(relevant)


def precision_at_k(retrieved: list[str], relevant: list[str], k: int | None = None) -> float:
    """Precision@K — 前 K 条 retrieved 中有多少是 relevant 的."""
    pool = retrieved[:k] if k else retrieved
    if not pool:
        return 0.0
    useful = sum(1 for r in pool if any(_is_match(r, tgt) for tgt in relevant))
    return useful / len(pool)


def mrr(retrieved: list[str], relevant: list[str]) -> float:
    """Mean Reciprocal Rank — 第一个命中 relevant 的位置倒数, 全没命中则 0."""
    for i, r in enumerate(retrieved, 1):
        if any(_is_match(r, tgt) for tgt in relevant):
            return 1.0 / i
    return 0.0


def f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)
