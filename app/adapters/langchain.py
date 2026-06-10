"""LangChain Adapter — MemoCortex 即 BaseChatMessageHistory 的替代品

用法:
    from app.adapters.langchain import MemoCortexChatHistory
    history = MemoCortexChatHistory(user_id="alice", session_id="s1")
    chain = RunnableWithMessageHistory(chain, lambda sid: history, ...)

设计:
  - add_message: 把消息内容写到 MemoCortex (按角色路由:
        user 消息 → episodic + 异步 semantic 抽取
        ai 消息 → episodic 但 importance 低)
  - messages property: 返回 working memory 最近若干条 + hybrid 召回的相关 semantic/episodic
  - clear: 清空 working memory
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from loguru import logger

from app.memories.working import working_memory
from app.models import MemoryRecord, MemoryType, WriteRequest
from app.orchestrator import orchestrator

if TYPE_CHECKING:
    pass


def _run_sync(coro):
    """LangChain BaseChatMessageHistory 接口是同步的, 把异步调用转同步."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在已运行的 loop 中 — 用 ensure_future + run_until_complete 会爆,
            # 简化处理: 用新 loop (MVP 阶段 LangChain 都是同步链)
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(coro)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


class MemoCortexChatHistory(BaseChatMessageHistory):
    """把对话历史落到 MemoCortex 的 5 类记忆系统.

    Args:
        user_id: 必填, 用户身份
        session_id: 会话 ID, 用于 Working Memory 隔离
        inject_profile: 是否在 messages 前置 SystemMessage 注入用户画像
        recall_k: messages 中召回相关历史的 top-k
    """

    def __init__(
        self,
        user_id: str,
        session_id: str = "default",
        inject_profile: bool = True,
        recall_k: int = 5,
    ) -> None:
        self.user_id = user_id
        self.session_id = session_id
        self.inject_profile = inject_profile
        self.recall_k = recall_k

    # ── BaseChatMessageHistory 接口 ────────────────────────────────────
    @property
    def messages(self) -> list[BaseMessage]:
        """返回完整对话上下文 — Working 短期 + Hybrid 召回 + 可选 Profile."""
        out: list[BaseMessage] = []

        # 1. 用户画像 → SystemMessage
        if self.inject_profile:
            try:
                profile = _run_sync(orchestrator.get_profile(self.user_id))
                p = profile.get("profile", {})
                if p and p.get("one_liner"):
                    out.append(
                        SystemMessage(
                            content=(
                                f"[用户画像] {p.get('one_liner', '')}\n"
                                f"偏好: {', '.join(p.get('preferences', []))}\n"
                                f"禁忌: {', '.join(p.get('constraints', []))}"
                            )
                        )
                    )
            except Exception as e:
                logger.debug(f"profile 注入失败 (非致命): {e}")

        # 2. Working Memory 按时序
        try:
            working = _run_sync(working_memory.read(self.user_id, self.session_id))
        except Exception:
            working = []
        for r in working:
            out.append(self._record_to_message(r))

        return out

    def add_message(self, message: BaseMessage) -> None:
        """LangChain 写入: 路由到 Working + Episodic + 异步 Semantic 抽取."""
        content = message.content if isinstance(message.content, str) else str(message.content)
        role = "user" if isinstance(message, HumanMessage) else "ai"
        importance = 0.5 if role == "user" else 0.3

        # 1. 写 Working (短期会话上下文)
        record = MemoryRecord(
            user_id=self.user_id,
            session_id=self.session_id,
            type=MemoryType.WORKING,
            content=f"[{role}] {content}",
            importance=importance,
            tags=[role],
        )
        try:
            _run_sync(working_memory.write(record))
        except Exception as e:
            logger.warning(f"working write 失败: {e}")

        # 2. 用户消息 → Episodic + 异步 Semantic
        if role == "user":
            try:
                _run_sync(
                    orchestrator.write(
                        WriteRequest(
                            user_id=self.user_id,
                            session_id=self.session_id,
                            content=content,
                            type=MemoryType.EPISODIC,
                            importance=importance,
                            tags=["user_message"],
                        )
                    )
                )
            except Exception as e:
                logger.warning(f"episodic write 失败: {e}")

    def clear(self) -> None:
        try:
            _run_sync(working_memory.clear(self.user_id, self.session_id))
        except Exception as e:
            logger.warning(f"clear 失败: {e}")

    # ── 内部 ──
    @staticmethod
    def _record_to_message(r: MemoryRecord) -> BaseMessage:
        text = r.content
        if text.startswith("[user]"):
            return HumanMessage(content=text[6:].strip())
        if text.startswith("[ai]"):
            return AIMessage(content=text[4:].strip())
        return AIMessage(content=text)
