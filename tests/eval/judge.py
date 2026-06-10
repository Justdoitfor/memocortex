"""LLM-as-Judge — 语义匹配判断召回结果是否覆盖期望答案

对 LongMemEval 这类需要"语义判分"的场景, 单靠字面匹配会漏判.
此 Judge 用 LLM (temperature=0 + Structured Output) 判断:
  - retrieved_context 中是否包含足以回答 question 的关键信息?
  - 与 expected_answer 是否一致?
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from loguru import logger
from pydantic import BaseModel, Field

from app.core.llm_factory import llm_factory


class JudgeVerdict(BaseModel):
    """LLM-as-Judge 输出."""

    correct: bool = Field(description="检索结果是否能正确回答问题")
    coverage_score: float = Field(ge=0.0, le=1.0, description="期望信息被覆盖的比例 0-1")
    reasoning: str = Field(description="一句话原因")


_JUDGE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "你是一个 Agent 记忆系统的评测裁判. 给定问题、期望答案、检索召回的记忆, "
                "判断这些记忆是否足以让 Agent 正确回答问题.\n"
                "\n"
                "评判规则:\n"
                "- correct=true: 召回记忆包含正确回答所需的关键事实\n"
                "- correct=false: 召回记忆缺失关键信息, 或与期望答案明显冲突\n"
                "- coverage_score: 期望答案中的关键信息被召回覆盖的比例\n"
                "- reasoning: 简明 (一句话)\n"
                "\n"
                "严格基于召回记忆判分, 不要靠常识脑补."
            ),
        ),
        (
            "human",
            (
                "问题: {question}\n\n"
                "期望答案 (Ground Truth):\n{expected_answer}\n\n"
                "Agent 召回的记忆 (Top {k}):\n{retrieved_block}"
            ),
        ),
    ]
)


async def judge(
    question: str,
    expected_answer: str,
    retrieved_texts: list[str],
) -> JudgeVerdict:
    """对一次召回做 LLM 评判."""
    retrieved_block = "\n".join(
        f"  [{i + 1}] {t[:300]}" for i, t in enumerate(retrieved_texts)
    ) or "(空)"

    try:
        llm = llm_factory.create_chat_model(temperature=0, streaming=False)
        chain = _JUDGE_PROMPT | llm.with_structured_output(
            JudgeVerdict, method="function_calling"
        )
        result = await chain.ainvoke(
            {
                "question": question,
                "expected_answer": expected_answer,
                "retrieved_block": retrieved_block,
                "k": len(retrieved_texts),
            }
        )
        if isinstance(result, dict):
            return JudgeVerdict(**result)
        return result
    except Exception as e:
        logger.warning(f"Judge LLM 失败, 降级用字面匹配: {e}")
        # 降级: 检查 expected_answer 的关键词是否在 retrieved 中
        key_terms = [t.strip() for t in expected_answer.split() if len(t) >= 2]
        hits = sum(
            1 for t in key_terms if any(t in r for r in retrieved_texts)
        )
        coverage = hits / max(len(key_terms), 1)
        return JudgeVerdict(
            correct=coverage >= 0.5,
            coverage_score=coverage,
            reasoning=f"LLM 不可用, 字面匹配覆盖 {coverage:.0%}",
        )
