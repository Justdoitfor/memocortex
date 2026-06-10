"""MemoCortex 冲突仲裁 Demo

演示 4 种 ConflictAction 各触发一次:
  REPLACE  — 用户搬家
  MERGE    — 用户新增过敏原
  VERSIONED — (启发式降级时演示, 需要更复杂的 Prompt 引导 LLM 选 VERSIONED)
  IGNORE   — 矛盾 / 低置信新事实

需要配 MEMOCORTEX_LLM_API_KEY (DeepSeek), 否则走启发式降级路径.

用法:
    uv run python examples/demo_conflict.py
"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import config
from app.models import MemoryType, WriteRequest
from app.orchestrator import orchestrator
from app.storage import get_metadata
from app.utils.logger import setup_logger


async def write_and_log(user_id: str, content: str) -> None:
    """同步走 SEMANTIC 路径 (LLM 抽取 + 仲裁), 而不是 EPISODIC 异步路径,
    保证 demo 中能立刻看到完整结果."""
    res = await orchestrator.write(
        WriteRequest(user_id=user_id, content=content, type=MemoryType.SEMANTIC)
    )
    arb_note = ""
    if res.arbitration:
        arb_note = f"  [arbitration={res.arbitration.action.value}]"
    print(f"  写入: {content}{arb_note}  → memory_id={res.memory_id[:8]}")


async def show_arbitrations(user_id: str) -> None:
    meta = get_metadata()
    items = await meta.list_arbitrations(user_id, limit=10)
    print(f"\n  → 用户 [{user_id}] 共 {len(items)} 条仲裁记录:")
    for a in reversed(items):
        print(
            f"     [{a['action']:9}] ({a['subject']}, {a['predicate']}): "
            f"{a['old_value']} → {a['new_value']}   "
            f"reason: {a['reasoning'][:50]}"
        )


async def show_facts(user_id: str) -> None:
    from app.storage import get_kg

    triples = await get_kg().find_triples(user_id, subject="user")
    print(f"\n  → 用户 [{user_id}] KG 中现存的 user 事实 ({len(triples)} 条):")
    by_pred: dict[str, list[str]] = {}
    for t in triples:
        by_pred.setdefault(t.predicate, []).append(t.object)
    for pred, vals in by_pred.items():
        print(f"     {pred}: {vals}")


async def main() -> None:
    setup_logger()
    await get_metadata().init_schema()

    if not config.llm_api_key:
        print("\n⚠️  MEMOCORTEX_LLM_API_KEY 未配置, 将走启发式降级路径")
        print("   要看完整 LLM-as-Arbitrator 效果, 请在 .env 配置 DeepSeek/OpenAI Key\n")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Conflict Arbitrator Demo — 4 种 Action")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    # 清空 demo 用户
    for uid in ["alice_replace", "alice_merge", "bob_conflict"]:
        try:
            await orchestrator.forget(user_id=uid, all_user_data=True)
        except Exception:
            pass

    # ─── Scenario 1: REPLACE (搬家) ───────────────────────────────────
    print("场景 1: REPLACE — 用户搬家")
    print("─" * 75)
    user = "alice_replace"
    await write_and_log(user, "我现在住在北京朝阳区")
    await write_and_log(user, "我搬家了, 现在住在上海浦东")
    await show_facts(user)
    await show_arbitrations(user)

    # ─── Scenario 2: MERGE (过敏原) ───────────────────────────────────
    print("\n\n场景 2: MERGE — 用户陆续提到多个过敏原")
    print("─" * 75)
    user = "alice_merge"
    await write_and_log(user, "我对花生过敏")
    await write_and_log(user, "其实我对芝麻也过敏")
    await write_and_log(user, "对了, 海鲜也不能吃, 也过敏")
    await show_facts(user)
    await show_arbitrations(user)

    # ─── Scenario 3: 多字段混合 ───────────────────────────────────────
    print("\n\n场景 3: 多字段混合 (跨多类型同时演示)")
    print("─" * 75)
    user = "bob_conflict"
    await write_and_log(user, "我叫 Bob, 30 岁, 在阿里巴巴做后端")
    await write_and_log(user, "我喜欢爬山和摄影")
    await write_and_log(user, "我刚跳槽了, 现在在字节跳动做 AI 工程师")  # → 应 REPLACE works_at
    await write_and_log(user, "我还喜欢打篮球")  # → 应 MERGE 到 likes
    await show_facts(user)
    await show_arbitrations(user)

    print("\n[OK] 冲突仲裁 Demo 完成. 查看 SQLite 的 arbitration_logs 表可获完整审计.\n")


if __name__ == "__main__":
    asyncio.run(main())
