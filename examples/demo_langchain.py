"""MemoCortex LangChain Adapter Demo — 跨 session 记忆持久

让一个 LangChain ChatBot 接入 MemoCortexChatHistory:
  - 第 1 个 session: 用户告诉 bot 一些偏好
  - 第 2 个 session: bot 在新会话中应能"记住"上次的偏好 (通过 Reflective Profile)

需要 MEMOCORTEX_LLM_API_KEY 才能跑完整链路. 没 key 时只演示记忆写入路径.

用法:
    uv run python examples/demo_langchain.py
"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from langchain_core.messages import AIMessage, HumanMessage

from app.adapters import MemoCortexChatHistory
from app.config import config
from app.orchestrator import orchestrator
from app.reflection import refresh_reflective_profile
from app.storage import get_metadata
from app.utils.logger import setup_logger


async def main() -> None:
    setup_logger()
    await get_metadata().init_schema()

    USER = "alice_langchain"

    # 清空
    try:
        await orchestrator.forget(user_id=USER, all_user_data=True)
    except Exception:
        pass

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  LangChain Adapter Demo — 跨 Session 长期记忆")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    # ── Session 1: 用户告诉 bot 自己的偏好 ──
    print("【Session 1】 用户告诉 bot 自己的偏好")
    history1 = MemoCortexChatHistory(user_id=USER, session_id="s1", inject_profile=True)
    history1.clear()  # 清掉历史

    msgs = [
        HumanMessage(content="你好, 我叫 Alice, 是一个 Python 工程师"),
        AIMessage(content="你好 Alice! 很高兴认识你"),
        HumanMessage(content="我对花生过敏, 同时我特别喜欢吃火锅"),
        AIMessage(content="好的, 我记住了你的过敏原和偏好"),
        HumanMessage(content="另外我住在杭州, 平时喜欢爬山"),
    ]
    for m in msgs:
        history1.add_message(m)
        prefix = "👤" if isinstance(m, HumanMessage) else "🤖"
        print(f"  {prefix} {m.content}")

    # 等 episodic 异步 semantic 抽取
    print("\n  ⏳ 等待后台 semantic 抽取 (5s)...")
    await asyncio.sleep(5.0)

    # 触发 Reflective 刷新
    if config.llm_api_key:
        print("\n  🧠 刷新用户画像 (Reflective Memory)...")
        profile = await refresh_reflective_profile(USER)
        print(f"  画像: {profile['profile']}")
    else:
        print("\n  ⚠️  无 LLM API Key, 跳过 Reflective 刷新")

    # ── Session 2: 新会话, 验证记忆是否生效 ──
    print("\n\n【Session 2】 全新会话 — 检查跨 session 记忆")
    history2 = MemoCortexChatHistory(user_id=USER, session_id="s2", inject_profile=True)
    history2.clear()

    # 取 messages 看看用户画像是否被自动注入
    msgs_loaded = history2.messages
    print(f"\n  Session 2 加载的上下文 ({len(msgs_loaded)} 条):")
    for m in msgs_loaded:
        print(f"    {type(m).__name__}: {m.content[:80]}")

    # 召回测试
    print("\n  🔍 召回测试: '用户能吃花生吗'")
    resp = await orchestrator.search(user_id=USER, query="用户能吃花生吗", top_k=3)
    for r in resp.results:
        print(f"    [{r.rank}] {r.record.content[:60]}   (score={r.signals.final_score:.3f})")

    print("\n[OK] 跨 session 长期记忆 demo 完成.\n")


if __name__ == "__main__":
    asyncio.run(main())
