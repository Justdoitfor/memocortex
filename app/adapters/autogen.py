"""AutoGen Adapter Stub — MVP 阶段未实现完整 Hook, 接口签名已就位

未来实现思路:
  - 给定 AutoGen Assistant Agent, 在 message lifecycle hook 中:
      a) on_message_received: 写 user 消息到 Episodic
      b) on_message_sent: 写 AI 消息 + 异步 semantic 抽取
      c) on_conversation_start: 召回相关历史注入 system_message
"""

from __future__ import annotations

from typing import Any


class MemoCortexHook:
    """AutoGen 集成 Hook (Stub).

    生产实现建议参考 mem0 的 autogen integration:
      https://docs.mem0.ai/integrations/autogen
    """

    def __init__(self, agent: Any, user_id: str) -> None:
        self._agent = agent
        self.user_id = user_id

    def register(self) -> None:
        raise NotImplementedError(
            "AutoGen Hook 未在 MVP 中实现. "
            "请用 LangChain Adapter 或直接调 SDK / MCP. "
            "Roadmap: https://github.com/your-org/memocortex/issues/12"
        )
