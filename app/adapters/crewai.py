"""CrewAI Adapter Stub — MVP 阶段未实现完整 Hook, 接口签名已就位

未来实现思路: 把 MemoCortex 作为 CrewAI Tool 暴露给 Agent, 让 Agent 自己决定调用时机.
"""

from __future__ import annotations


class MemoCortexCrewTool:
    """CrewAI Tool 封装 (Stub)."""

    name = "memocortex"
    description = "Long-term memory for the agent (5 layered memory types)."

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    def _run(self, query: str) -> str:
        raise NotImplementedError(
            "CrewAI Tool 未在 MVP 中实现. "
            "请用 LangChain Adapter 或直接调 SDK / MCP. "
            "Roadmap: https://github.com/your-org/memocortex/issues/13"
        )
