"""/admin — 反思手动触发 / 仲裁日志查询 / Eval 入口 (含 SSE 流式跑分)"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from app.reflection import run_all_for_user
from app.storage import get_metadata

router = APIRouter()


@router.post("/reflect/{user_id}", summary="手动触发用户的全部反思任务")
async def trigger_reflection(user_id: str) -> dict:
    return await run_all_for_user(user_id)


@router.get("/arbitrations/{user_id}", summary="查询冲突仲裁审计日志")
async def list_arbitrations(user_id: str, limit: int = 50) -> dict:
    meta = get_metadata()
    items = await meta.list_arbitrations(user_id, limit=limit)
    return {"user_id": user_id, "count": len(items), "items": items}


@router.get("/eval/last/{suite}", summary="查询某 suite 的上次 eval 跑分")
async def get_last_eval(suite: str) -> dict:
    meta = get_metadata()
    last = await meta.last_eval(suite)
    return last or {"suite": suite, "score": None, "message": "无历史 eval 记录"}


@router.get("/eval/history/{suite}", summary="查询某 suite 的历史跑分 (供趋势图)")
async def get_eval_history(suite: str, limit: int = 20) -> dict:
    meta = get_metadata()
    runs = await meta.list_eval_runs(suite, limit=limit)
    # 翻转为时间正序方便前端画图
    return {"suite": suite, "runs": list(reversed(runs))}


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                     SSE 流式跑 Eval                                   ║
# ╚══════════════════════════════════════════════════════════════════════╝


async def _stream_cn_scenarios() -> AsyncIterator[dict]:
    """yield 每个 scenario 完成的 SSE 事件."""
    import glob
    import time as _time
    from pathlib import Path

    from app.models import MemoryType, WriteRequest
    from app.orchestrator import orchestrator

    scenarios_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "eval" / "cn_scenarios" / "data"
    files = sorted(glob.glob(str(scenarios_dir / "scenario_*.json")))

    yield {"event": "start", "data": json.dumps({
        "suite": "cn_scenarios", "total": len(files)
    })}

    results: list[dict] = []
    for idx, fp in enumerate(files, 1):
        with open(fp, encoding="utf-8") as f:
            sc = json.load(f)
        user_id = sc["user_id"]
        try:
            await orchestrator.forget(user_id=user_id, all_user_data=True)
        except Exception:
            pass

        start = _time.perf_counter()
        for w in sc["writes"]:
            await orchestrator.write(WriteRequest(
                user_id=user_id, content=w["content"],
                type=MemoryType(w.get("type", "semantic")),
            ))
        await orchestrator.wait_pending(timeout=15.0)
        await asyncio.sleep(0.3)

        resp = await orchestrator.search(user_id=user_id, query=sc["query"], top_k=5)
        latency = (_time.perf_counter() - start) * 1000
        top_3 = [r.record.content for r in resp.results[:3]]

        # 判分
        checks: dict = {}
        if sc.get("must_contain_all"):
            missing = [t for t in sc["must_contain_all"]
                       if not any(t in r for r in top_3)]
            checks["contain"] = {"pass": not missing, "missing": missing}
        if sc.get("must_not_contain_in_top_3"):
            violated = [t for t in sc["must_not_contain_in_top_3"]
                        if any(t in r for r in top_3)]
            checks["not_contain"] = {"pass": not violated, "violated": violated}
        if sc.get("expected_action"):
            arbs = await get_metadata().list_arbitrations(user_id, limit=5)
            actions = [a["action"] for a in arbs]
            checks["action"] = {
                "expected": sc["expected_action"],
                "actual": actions[:3],
                "pass": sc["expected_action"] in actions,
            }
        all_pass = all(c.get("pass", False) for c in checks.values()) if checks else True

        result = {
            "index": idx,
            "id": sc["id"],
            "name": sc["name"],
            "pass": all_pass,
            "latency_ms": round(latency, 1),
            "top_3": top_3,
            "checks": checks,
        }
        results.append(result)

        yield {"event": "item", "data": json.dumps(result, ensure_ascii=False)}

    passed = sum(1 for r in results if r["pass"])
    rate = passed / len(results) if results else 0.0
    # 落盘
    try:
        await get_metadata().save_eval_run(
            "cn_scenarios", rate, {"results": results, "passed": passed, "total": len(results)}
        )
    except Exception:
        pass

    yield {"event": "done", "data": json.dumps({
        "passed": passed, "total": len(results), "pass_rate": rate,
    })}


async def _stream_longmemeval() -> AsyncIterator[dict]:
    """yield 每个 LongMemEval-style 题完成的 SSE 事件."""
    import time as _time

    from app.models import MemoryType, WriteRequest
    from app.orchestrator import orchestrator
    from tests.eval.longmemeval.adapter import is_available
    from tests.eval.longmemeval.runner import load_dataset

    if not is_available():
        yield {"event": "error", "data": json.dumps({
            "message": "LongMemEval 数据集未生成. 先跑: python -m tests.eval.longmemeval.build_dataset"
        })}
        return

    dataset = load_dataset()
    yield {"event": "start", "data": json.dumps({
        "suite": "longmemeval_cn30", "total": len(dataset),
    })}

    results: list[dict] = []
    for idx, item in enumerate(dataset, 1):
        user_id = item["user_id"]
        try:
            await orchestrator.forget(user_id=user_id, all_user_data=True)
        except Exception:
            pass

        start = _time.perf_counter()
        for msg in item["sessions"]:
            if msg["role"] != "user":
                continue
            await orchestrator.write(WriteRequest(
                user_id=user_id, content=msg["content"], type=MemoryType.EPISODIC,
            ))
        await orchestrator.wait_pending(timeout=30.0)

        resp = await orchestrator.search(user_id=user_id, query=item["question"], top_k=5)
        latency = (_time.perf_counter() - start) * 1000
        texts = [r.record.content for r in resp.results]
        top_3 = texts[:3]

        # 判分
        checks: dict = {}
        must_contain = item.get("must_contain", [])
        missing = [t for t in must_contain
                   if not any(t.lower() in r.lower() for r in texts)]
        checks["contain"] = {"pass": not missing, "missing": missing}
        must_not = item.get("must_not_contain", [])
        if must_not:
            violated = [t for t in must_not
                        if any(t.lower() in r.lower() for r in top_3)]
            checks["not_contain"] = {"pass": not violated, "violated": violated}
        all_pass = all(c.get("pass", False) for c in checks.values())

        result = {
            "index": idx,
            "question_id": item["question_id"],
            "subtype": item["subtype"],
            "pass": all_pass,
            "latency_ms": round(latency, 1),
            "top_3": top_3,
        }
        results.append(result)
        yield {"event": "item", "data": json.dumps(result, ensure_ascii=False)}

    # 按子维度汇总
    from collections import defaultdict
    by_sub: dict[str, list] = defaultdict(list)
    for r in results:
        by_sub[r["subtype"]].append(r)
    by_subtype = {
        st: {"passed": sum(1 for r in rs if r["pass"]), "total": len(rs)}
        for st, rs in by_sub.items()
    }
    passed = sum(1 for r in results if r["pass"])
    rate = passed / len(results) if results else 0.0

    try:
        await get_metadata().save_eval_run(
            "longmemeval_cn30", rate,
            {"by_subtype": by_subtype, "passed": passed, "total": len(results)},
        )
    except Exception:
        pass

    yield {"event": "done", "data": json.dumps({
        "passed": passed, "total": len(results), "pass_rate": rate,
        "by_subtype": by_subtype,
    })}


@router.get(
    "/eval/run",
    summary="SSE 流式跑 eval (suite=cn_scenarios | longmemeval)",
)
async def run_eval_stream(suite: str = Query(...)) -> EventSourceResponse:
    """流式跑 eval, 每题完成 SSE 推一行. 前端用 EventSource 接."""
    if suite == "cn_scenarios":
        gen = _stream_cn_scenarios()
    elif suite in ("longmemeval", "longmemeval_cn30"):
        gen = _stream_longmemeval()
    else:
        raise HTTPException(400, f"未知 suite: {suite}")
    return EventSourceResponse(gen)
