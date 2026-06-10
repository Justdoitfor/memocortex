"""LLM 工厂 — OpenAI 兼容协议, 支持 DeepSeek / OpenAI / DashScope / 等价厂商

设计借鉴 SuperBizAgent: 单一 create_chat_model() 入口, 通过 .env 切厂商不改代码.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from loguru import logger

from app.config import config


class LLMFactory:
    """LLM 工厂 — 通过 OpenAI 兼容模式接入任意厂商.

    切换厂商只改 .env:
      DeepSeek:  MEMOCORTEX_LLM_API_BASE=https://api.deepseek.com/v1
      OpenAI:    MEMOCORTEX_LLM_API_BASE=https://api.openai.com/v1
      DashScope: MEMOCORTEX_LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
    """

    @staticmethod
    def create_chat_model(
        model: str | None = None,
        temperature: float = 0.0,
        streaming: bool = False,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> ChatOpenAI:
        """创建 ChatOpenAI 实例.

        Args:
            model: 模型名, None 用 config.llm_model
            temperature: 默认 0 (仲裁/抽取需要可复现)
            streaming: 是否启用流式
            timeout: 单次调用超时秒数
            max_retries: 失败重试次数 (LangChain 内置指数退避)
        """
        resolved_model = model or config.llm_model
        if not config.llm_api_key:
            logger.warning(
                "MEMOCORTEX_LLM_API_KEY 未配置, LLM 调用会失败. "
                "Eval / Arbitrator 等需要 LLM 的功能将不可用."
            )

        return ChatOpenAI(
            model=resolved_model,
            temperature=temperature,
            streaming=streaming,
            base_url=config.llm_api_base,
            api_key=config.llm_api_key,
            timeout=timeout,
            max_retries=max_retries,
        )


llm_factory = LLMFactory()
