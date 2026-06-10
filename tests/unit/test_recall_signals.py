"""单元测试: 4 信号召回打分

无需 LLM / ChromaDB, 纯函数测试.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models import MemoryRecord, MemoryType
from app.recall.signals import (
    compute_graph_proximity,
    compute_importance,
    compute_temporal_decay,
    compute_vector_sim,
    fuse_signals,
)


def test_vector_sim_clamps_to_unit_range():
    assert compute_vector_sim(0.5) == 0.5
    assert compute_vector_sim(-0.1) == 0.0
    assert compute_vector_sim(1.5) == 1.0


def test_temporal_decay_now_returns_one():
    now = datetime.now()
    assert abs(compute_temporal_decay(now, now=now) - 1.0) < 1e-6


def test_temporal_decay_old_decreases():
    now = datetime.now()
    one_tau_ago = now - timedelta(days=30)  # 默认 tau=30 → e^{-1} ≈ 0.37
    score = compute_temporal_decay(one_tau_ago, now=now, tau_days=30.0)
    assert 0.35 <= score <= 0.40


def test_temporal_decay_tau_zero():
    """tau=0 应直接返回 1, 不爆 0 除."""
    assert compute_temporal_decay(datetime.now(), tau_days=0.0) == 1.0


def test_graph_proximity_full_score_on_subject_object_match():
    record = MemoryRecord(
        user_id="u",
        type=MemoryType.SEMANTIC,
        content="x",
        structured={"subject": "user", "object": "北京"},
    )
    score = compute_graph_proximity(record, query_entities={"北京"}, user_neighbors=set())
    assert score == 0.5


def test_graph_proximity_zero_on_no_overlap():
    record = MemoryRecord(
        user_id="u",
        type=MemoryType.SEMANTIC,
        content="x",
        structured={"subject": "user", "object": "上海"},
    )
    score = compute_graph_proximity(
        record, query_entities={"北京"}, user_neighbors={"工作"}
    )
    assert score == 0.0


def test_importance_with_recall_count_saturation():
    record = MemoryRecord(
        user_id="u",
        type=MemoryType.EPISODIC,
        content="x",
        importance=0.5,
        recall_count=0,
    )
    base = compute_importance(record)
    assert base == 0.5

    record.recall_count = 100
    boosted = compute_importance(record)
    assert boosted > base
    assert boosted <= 1.0


def test_fuse_signals_default_weights():
    score = fuse_signals(
        vector_sim=1.0, temporal_decay=1.0, graph_proximity=1.0, importance=1.0
    )
    # 总和 1.0, 所有信号满分, 应得 1.0
    assert abs(score - 1.0) < 1e-6


def test_fuse_signals_custom_weights():
    score = fuse_signals(
        vector_sim=1.0,
        temporal_decay=0.0,
        graph_proximity=0.0,
        importance=0.0,
        weights=(1.0, 0.0, 0.0, 0.0),
    )
    assert score == 1.0


def test_fuse_signals_zero_total_weights_returns_zero():
    """0 总权重时返回 0 — 语义: 没有任何信号被采用."""
    score = fuse_signals(
        vector_sim=1.0,
        temporal_decay=1.0,
        graph_proximity=1.0,
        importance=1.0,
        weights=(0.0, 0.0, 0.0, 0.0),
    )
    assert score == 0.0
