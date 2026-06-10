"""Agent 框架适配器子包

- LangChain: 已实现 (BaseChatMessageHistory 接口)
- AutoGen / CrewAI: Stub, MVP 阶段未实现, 接口签名占位
"""

from app.adapters.langchain import MemoCortexChatHistory

__all__ = ["MemoCortexChatHistory"]
