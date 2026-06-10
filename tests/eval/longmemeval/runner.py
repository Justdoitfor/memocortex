"""LongMemEval-style 数据集 loader + runner

加载 data/cn_30.json, 对每题:
  1. 清空该 user 历史
  2. 按 sessions 顺序写入 (走 SEMANTIC 路径, LLM 自动抽取 + 仲裁)
  3. 提问, 拿 top-K 召回
  4. 三层判分:
     - must_contain  → 关键词在 top-K 召回中
     - must_not_contain → 反例不应出现 (KU 子维度专用)
     - LLM-as-Judge   → 召回内容能否真正回答 question

汇总按 subtype 分维度统计 + 总分.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

# Windows GBK 兜底
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.models import MemoryType, WriteRequest
from app.orchestrator import orchestrator
from app.storage import get_metadata

_HERE = Path(__file__).resolve().parent
DATA_PATH = _HERE / "data" / "cn_30.json"


def is_available() -> bool:
    return DATA_PATH.exists()


def load_dataset() -> list[dict[str, Any]]:
    if not is_available():
        raise FileNotFoundError(
            f"{DATA_PATH} 不存在. 先执行: "
            "uv run python -m tests.eval.longmemeval.build_dataset"
        )
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


async def run_one(item: dict[str, Any], use_llm_judge: bool = False) -> dict[str, Any]:
    """跑一道题, 返回评测结果."""
    user_id = item["user_id"]

    # 1. 清空隔离
    try:
        await orchestrator.forget(user_id=user_id, all_user_data=True)
    except Exception:
        pass

    # 2. 顺序写入 sessions (只写 user 角色的, ai 是 distractor 应答, 不写入)
    #    每条同时:
    #      a) Episodic 写入 — 保留原文, 用于关键词召回
    #      b) Semantic 抽取 — LLM 自动提取结构化 fact, 用于精准回答
    start = time.perf_counter()
    for msg in item["sessions"]:
        if msg["role"] != "user":
            continue
        await orchestrator.write(
            WriteRequest(
                user_id=user_id,
                content=msg["content"],
                type=MemoryType.EPISODIC,
            )
        )

    # 等所有后台 Semantic 抽取任务完成 (REPLACE/MERGE 决策必须在召回前生效)
    await orchestrator.wait_pending(timeout=30.0)

    # 3. 召回 (top-5, 不限类型)
    resp = await orchestrator.search(
        user_id=user_id, query=item["question"], top_k=5
    )
    latency_ms = (time.perf_counter() - start) * 1000

    retrieved_texts = [r.record.content for r in resp.results]
    top_3 = retrieved_texts[:3]

    # 4. 多层判分
    checks: dict[str, Any] = {}

    # 4a. must_contain 在 top-5 任意一条
    must_contain = item.get("must_contain", [])
    missing = [
        t for t in must_contain
        if not any(t.lower() in r.lower() for r in retrieved_texts)
    ]
    checks["contain"] = {"pass": len(missing) == 0, "missing": missing}

    # 4b. must_not_contain 不应在 top-3 出现 (KU 专用)
    must_not = item.get("must_not_contain", [])
    if must_not:
        violated = [
            t for t in must_not
            if any(t.lower() in r.lower() for r in top_3)
        ]
        checks["not_contain"] = {"pass": len(violated) == 0, "violated": violated}

    # 4c. (可选) LLM-as-Judge
    if use_llm_judge:
        from tests.eval.judge import judge
        verdict = await judge(
            question=item["question"],
            expected_answer=item["expected_answer"],
            retrieved_texts=retrieved_texts,
        )
        checks["judge"] = {
            "pass": verdict.correct,
            "coverage_score": verdict.coverage_score,
            "reasoning": verdict.reasoning,
        }

    all_pass = all(c.get("pass", False) for c in checks.values())

    return {
        "question_id": item["question_id"],
        "subtype": item["subtype"],
        "pass": all_pass,
        "latency_ms": round(latency_ms, 1),
        "top_3": top_3,
        "checks": checks,
        "question": item["question"],
        "expected_answer": item["expected_answer"],
    }


async def run_suite(use_llm_judge: bool = False, limit: int | None = None) -> dict[str, Any]:
    """跑全部 30 题. limit 控制只跑前 N 题, 调试用."""
    await get_metadata().init_schema()
    dataset = load_dataset()
    if limit:
        dataset = dataset[:limit]

    print(f"\n{'=' * 80}")
    print(f"  Suite: LongMemEval-style 中文长记忆 ({len(dataset)} 题, "
          f"judge={'on' if use_llm_judge else 'off'})")
    print(f"{'=' * 80}")

    results: list[dict[str, Any]] = []
    for i, item in enumerate(dataset, 1):
        print(f"  [{i:>2}/{len(dataset)}] {item['question_id']:<14} {item['subtype']:<22} ...",
              end=" ", flush=True)
        try:
            res = await run_one(item, use_llm_judge=use_llm_judge)
            tag = "[PASS]" if res["pass"] else "[FAIL]"
            print(f"{tag}  ({res['latency_ms']:.0f}ms)")
            if not res["pass"]:
                for cn, cr in res["checks"].items():
                    if not cr.get("pass", True):
                        print(f"          x {cn}: {cr}")
            results.append(res)
        except Exception as e:
            print(f"[ERROR] {e}")
            results.append({
                "question_id": item["question_id"],
                "subtype": item["subtype"],
                "pass": False,
                "error": str(e),
            })

    # 按 subtype 分维度统计
    by_sub: dict[str, list] = defaultdict(list)
    for r in results:
        by_sub[r["subtype"]].append(r)

    print(f"\n{'-' * 80}")
    print(f"  分维度通过率:")
    for st, rs in sorted(by_sub.items()):
        passed = sum(1 for r in rs if r.get("pass"))
        rate = passed / len(rs) if rs else 0.0
        print(f"    {st:<22} {passed:>2}/{len(rs):<2} = {rate * 100:>3.0f}%")

    total_passed = sum(1 for r in results if r.get("pass"))
    total_rate = total_passed / len(results) if results else 0.0
    print(f"{'-' * 80}")
    print(f"  总分: {total_passed}/{len(results)} = {total_rate * 100:.0f}%")
    print(f"{'=' * 80}\n")

    return {
        "suite": "longmemeval_cn30",
        "total": len(results),
        "passed": total_passed,
        "pass_rate": total_rate,
        "by_subtype": {
            st: {"passed": sum(1 for r in rs if r.get("pass")), "total": len(rs)}
            for st, rs in by_sub.items()
        },
        "results": results,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 题")
    parser.add_argument("--judge", action="store_true", help="启用 LLM-as-Judge (慢)")
    args = parser.parse_args()

    report = asyncio.run(run_suite(use_llm_judge=args.judge, limit=args.limit))

    # 写入 SQLite eval_runs + 落盘
    async def _save():
        meta = get_metadata()
        await meta.save_eval_run(
            "longmemeval_cn30",
            report["pass_rate"],
            {
                "by_subtype": report["by_subtype"],
                "total": report["total"],
            },
        )

    asyncio.run(_save())

    score_file = _HERE / ".last_longmem_score"
    with open(score_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"评分已保存: {score_file}")


if __name__ == "__main__":
    main()
