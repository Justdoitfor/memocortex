"""单元测试: Eval 指标"""

from __future__ import annotations

from tests.eval.metrics import f1, mrr, precision_at_k, recall_at_k


def test_recall_at_k_full_hit():
    assert recall_at_k(["北京风景", "上海美食"], ["北京"]) == 1.0


def test_recall_at_k_partial():
    """两个 target, 只命中一个."""
    assert recall_at_k(["北京风景"], ["北京", "上海"]) == 0.5


def test_recall_at_k_empty_relevant_returns_one():
    """relevant 为空时按定义 trivial pass."""
    assert recall_at_k(["x"], []) == 1.0


def test_precision_at_k_basic():
    """3 条 retrieved, 2 条相关."""
    p = precision_at_k(["北京", "上海", "杭州"], ["北京", "上海"])
    assert abs(p - 2 / 3) < 1e-6


def test_precision_at_k_empty_retrieved():
    assert precision_at_k([], ["x"]) == 0.0


def test_mrr_first_hit_at_position_2():
    assert mrr(["杭州天气", "北京天气"], ["北京"]) == 0.5


def test_mrr_no_hit():
    assert mrr(["杭州", "上海"], ["北京"]) == 0.0


def test_mrr_first_hit_at_1():
    assert mrr(["北京", "上海"], ["北京"]) == 1.0


def test_f1():
    assert f1(0.0, 0.0) == 0.0
    assert abs(f1(0.5, 0.5) - 0.5) < 1e-6
    assert abs(f1(1.0, 1.0) - 1.0) < 1e-6
