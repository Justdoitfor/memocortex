"""中文场景 Eval Runner

对每个 scenario_*.json:
  1. 清空该 user 的所有记忆
  2. 按 writes 顺序写入 (走 Orchestrator, 走完整流程含 semantic 抽取 + 仲裁)
  3. 等待异步任务完成
  4. 执行 query, 拿到 top-K
  5. 多维度判分:
     - must_contain_all 关键词全在 top-3 → pass
     - must_not_contain_in_top_3 关键词不在 top-3 → pass
     - 期望 action 与最近一次仲裁日志的 action 一致 → pass
  6. 汇总输出 + 落盘 .last_eval_score
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Windows 终端 GBK 编码兜底
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.models import MemoryType, WriteRequest
from app.orchestrator import orchestrator
from app.storage import get_metadata
from app.utils.logger import setup_logger

setup_logger()

_HERE = Path(__file__).resolve().parent
SCENARIO_DIRS = {
    "cn_scenarios": _HERE / "cn_scenarios" / "data",
    "longmemeval": _HERE / "longmemeval" / "data",
}
LAST_SCORE_FILE = _HERE / ".last_eval_score"


# ── 单场景执行 ───────────────────────────────────────────────────────


async def run_cn_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """跑一个中文场景, 返回结构化结果."""
    user_id = scenario["user_id"]
    name = scenario["name"]

    # 1. 清空该用户历史 (隔离场景)
    try:
        await orchestrator.forget(user_id=user_id, all_user_data=True)
    except Exception:
        pass

    # 2. 按序写入 — 走 SEMANTIC 路径确保 LLM 抽取 + 仲裁同步完成 (可复现)
    start = time.perf_counter()
    for w in scenario["writes"]:
        await orchestrator.write(
            WriteRequest(
                user_id=user_id,
                content=w["content"],
                type=MemoryType(w.get("type", "semantic")),
            )
        )

    # 兜底等一下 (其实 SEMANTIC 已经 sync 了)
    await asyncio.sleep(0.5)

    # 3. 召回
    resp = await orchestrator.search(
        user_id=user_id, query=scenario["query"], top_k=5
    )
    latency = (time.perf_counter() - start) * 1000

    # 4. 提取 top-3 的文本
    top_texts = [r.record.content for r in resp.results[:3]]

    # 5. 判分
    checks: dict[str, Any] = {}

    if scenario.get("must_contain_all"):
        missing = [
            t for t in scenario["must_contain_all"]
            if not any(t in r for r in top_texts)
        ]
        checks["must_contain_all"] = {
            "pass": len(missing) == 0,
            "missing": missing,
        }

    if scenario.get("must_not_contain_in_top_3"):
        violated = [
            t for t in scenario["must_not_contain_in_top_3"]
            if any(t in r for r in top_texts)
        ]
        checks["must_not_contain_in_top_3"] = {
            "pass": len(violated) == 0,
            "violated": violated,
        }

    # 期望 action 校验
    if scenario.get("expected_action"):
        meta = get_metadata()
        arbs = await meta.list_arbitrations(user_id, limit=5)
        actual_actions = [a["action"] for a in arbs]
        checks["expected_action"] = {
            "expected": scenario["expected_action"],
            "actual_recent": actual_actions[:3],
            "pass": scenario["expected_action"] in actual_actions,
        }

    all_pass = all(c.get("pass", False) for c in checks.values()) if checks else True

    return {
        "id": scenario["id"],
        "name": name,
        "pass": all_pass,
        "latency_ms": round(latency, 1),
        "top_3": top_texts,
        "checks": checks,
    }


# ── 套件 ──────────────────────────────────────────────────────────────


async def run_suite_cn() -> dict[str, Any]:
    files = sorted(glob.glob(str(SCENARIO_DIRS["cn_scenarios"] / "scenario_*.json")))
    if not files:
        print("[cn_scenarios] 无场景文件")
        return {"suite": "cn_scenarios", "results": [], "pass_rate": 0.0}

    print(f"\n{'=' * 80}")
    print(f"  Suite: cn_scenarios  ({len(files)} 个场景)")
    print(f"{'=' * 80}")

    results: list[dict[str, Any]] = []
    for f in files:
        with open(f, encoding="utf-8") as fp:
            sc = json.load(fp)
        print(f"  [{sc['id']}] {sc['name']:<35} ...", end=" ", flush=True)
        try:
            res = await run_cn_scenario(sc)
            emoji = "[PASS]" if res["pass"] else "[FAIL]"
            print(f"{emoji}  ({res['latency_ms']:.0f}ms)")
            for cname, cres in res["checks"].items():
                if not cres.get("pass", True):
                    print(f"        x {cname}: {cres}")
            results.append(res)
        except Exception as e:
            print(f"[ERROR] {e}")
            results.append({"id": sc["id"], "name": sc["name"], "pass": False, "error": str(e)})

    passed = sum(1 for r in results if r.get("pass"))
    pass_rate = passed / len(results) if results else 0.0

    print(f"\n  通过: {passed}/{len(results)}  =  {pass_rate * 100:.0f}%")
    print(f"{'=' * 80}\n")

    return {
        "suite": "cn_scenarios",
        "total": len(results),
        "passed": passed,
        "pass_rate": pass_rate,
        "results": results,
    }


async def run_suite_longmemeval() -> dict[str, Any]:
    """LongMemEval-style 中文长记忆子集 — 30 题."""
    from tests.eval.longmemeval.adapter import is_available
    from tests.eval.longmemeval.runner import run_suite as run_longmem_suite

    if not is_available():
        print("[longmemeval] 数据集未生成. 执行: "
              "uv run python -m tests.eval.longmemeval.build_dataset")
        return {"suite": "longmemeval_cn30", "skipped": True, "pass_rate": 0.0}
    return await run_longmem_suite(use_llm_judge=False)


# ── 主入口 ────────────────────────────────────────────────────────────


def _save_last_score(report: dict[str, Any]) -> None:
    LAST_SCORE_FILE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _load_last_score() -> dict[str, Any] | None:
    if LAST_SCORE_FILE.exists():
        try:
            return json.loads(LAST_SCORE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None


async def main_async(suite: str) -> None:
    await get_metadata().init_schema()

    report: dict[str, Any] = {"timestamp": datetime.now().isoformat(), "suites": {}}

    prev = _load_last_score()

    if suite in ("all", "cn_scenarios"):
        cn = await run_suite_cn()
        report["suites"]["cn_scenarios"] = cn
        # 写 SQLite 历史
        try:
            await get_metadata().save_eval_run(
                "cn_scenarios", cn["pass_rate"], {"results": cn["results"]}
            )
        except Exception:
            pass

    if suite in ("all", "longmemeval"):
        lme = await run_suite_longmemeval()
        report["suites"]["longmemeval"] = lme

    _save_last_score(report)

    # 跨版本对比
    if prev:
        for sname, current in report["suites"].items():
            prev_data = prev.get("suites", {}).get(sname, {})
            prev_rate = prev_data.get("pass_rate", 0.0)
            cur_rate = current.get("pass_rate", 0.0)
            delta = cur_rate - prev_rate
            sym = "UP" if delta > 0 else ("DOWN" if delta < 0 else "==")
            print(
                f"[{sname}] 本次 {cur_rate * 100:.0f}%  "
                f"上次 {prev_rate * 100:.0f}%  {sym} {delta * 100:+.0f}%"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="MemoCortex Eval Runner")
    parser.add_argument(
        "--suite",
        choices=["all", "cn_scenarios", "longmemeval"],
        default="all",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.suite))


if __name__ == "__main__":
    main()
