"""MemoCortex MCP Server — MCP-Native Long-Term Memory (Phase 4)

工具 (动词驱动, 符合 MCP 语义习惯, 对齐 MemoryMesh §9.1 设计):
  - remember            主动写入记忆 (替代 memory_write)
  - recall              检索相关记忆 (替代 memory_search)
  - recall_workflow     检索程序性记忆 (Procedural)
  - get_profile         获取用户画像 (Reflective)
  - track_signal        上报行为信号 (Phase 2)
  - reflect             触发 Pattern Miner
  - manage_memory       记忆管理 (list/forget/mark_stale)
  - list_arbitrations   查询冲突审计 (调试)

MCP Resources (除 Tools 外, 可供 Agent 在 SystemPrompt 中注入):
  - memory://summary/{user_id}    用户核心 Semantic 摘要
  - memory://profile/{user_id}    用户画像 JSON
  - memory://workflows/{user_id}  Procedural 索引

启动:
  uv run python -m mcp_server.server
  → http://127.0.0.1:8766/mcp

接入 Claude Desktop:
  {
    "mcpServers": {
      "memocortex": {
        "url": "http://127.0.0.1:8766/mcp",
        "transport": "streamable-http"
      }
    }
  }
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastmcp import FastMCP
from loguru import logger

from app.config import config
from app.models import (
    MemoryType,
    SearchRequest,
    SignalType,
    WriteRequest,
)
from app.orchestrator import orchestrator
from app.storage import get_metadata
from app.utils.logger import setup_logger

setup_logger()
mcp = FastMCP("MemoCortex")


def _run(coro):
    """同步桥 — fastmcp 当前版本工具签名是同步的."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio

            nest_asyncio.apply()
            return loop.run_until_complete(coro)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                     核心 MCP 工具 (动词驱动)                          ║
# ╚══════════════════════════════════════════════════════════════════════╝


@mcp.tool()
def remember(
    user_id: str,
    content: str,
    memory_type: str = "episodic",
    importance: str = "medium",
    context: str | None = None,
    source_type: str | None = None,
    conflict_strategy: str = "arbitrator",
) -> dict[str, Any]:
    """将重要信息存入长期记忆.

    适用场景: 用户提供了个人信息、偏好、工作上下文, 或完成了一项值得记录的任务.
    不需要每次消息时调用, 只在信息具有跨会话价值时使用.

    Args:
        user_id: 用户标识
        content: 要记忆的核心信息 (自然语言)
        memory_type: episodic / semantic / procedural (默认 episodic)
            注: reflective 由 Worker 自动生成, implicit 由 Pattern Miner 挖掘, 不可手动写
        importance: low / medium / high — 影响 decay rate 与召回排序
        context: 可选, 补充上下文场景
        source_type: explicit_statement (默认) / agent_confirmed / inferred / corrected
        conflict_strategy: arbitrator (LLM 决策) / staleness (软废弃) / auto
    """
    try:
        mtype = MemoryType(memory_type.lower())
        if mtype in (MemoryType.REFLECTIVE, MemoryType.IMPLICIT, MemoryType.WORKING):
            return {
                "error": f"memory_type='{mtype.value}' 不可手动写. "
                         f"Reflective 由 Worker 聚合, Implicit 由 Pattern Miner 挖掘, "
                         f"Working 不对外暴露."
            }
    except ValueError:
        return {"error": f"非法 memory_type: {memory_type}, 支持: episodic/semantic/procedural"}

    imp_map = {"low": 0.3, "medium": 0.5, "high": 0.8}
    req = WriteRequest(
        user_id=user_id,
        content=content if not context else f"{content}\n[context: {context}]",
        type=mtype,
        importance=imp_map.get(importance.lower(), 0.5),
        source_type=source_type,
        conflict_strategy=conflict_strategy,
    )
    res = _run(orchestrator.write(req))
    return res.model_dump(mode="json")


@mcp.tool()
def recall(
    user_id: str,
    query: str,
    memory_types: list[str] | None = None,
    top_k: int = 5,
    min_confidence: float = 0.55,
) -> dict[str, Any]:
    """在回答用户问题前, 检索可能相关的历史记忆.

    适用场景: 用户询问之前讨论过的话题、个人偏好、需要保持上下文一致性时.
    返回结果含 4 信号融合分数 (vector / temporal / bm25 / importance) 可解释.

    Args:
        user_id: 用户标识
        query: 检索关键词或问题
        memory_types: 可选, 限定类型 (episodic/semantic/procedural/reflective/implicit)
        top_k: 默认 5
        min_confidence: vector_sim 阈值, 默认 0.55 (低于则视为无关 → 返回空)
    """
    parsed_types: list[MemoryType] | None = None
    if memory_types:
        try:
            parsed_types = [MemoryType(t.lower()) for t in memory_types]
            for t in parsed_types:
                if t == MemoryType.WORKING:
                    return {"error": "Working 不对外暴露"}
        except ValueError as e:
            return {"error": str(e)}

    req = SearchRequest(
        user_id=user_id,
        query=query,
        types=parsed_types,
        top_k=top_k,
        score_threshold=min_confidence,
    )
    res = _run(
        orchestrator.search(
            user_id=req.user_id,
            query=req.query,
            types=req.types,
            top_k=req.top_k,
            session_id=req.session_id,
            score_threshold=req.score_threshold,
        )
    )
    return res.model_dump(mode="json")


@mcp.tool()
def recall_workflow(
    user_id: str,
    trigger_context: str,
    top_k: int = 3,
) -> dict[str, Any]:
    """检索用户在特定场景下的工作流程和操作规范 (Procedural Memory).

    适用场景: 用户要求执行某类任务时, 先查是否有定制化工作流偏好.
    返回结构化步骤而非自由文本, 便于 Agent 直接执行.

    Args:
        user_id: 用户标识
        trigger_context: 任务场景描述, 如 'code review' / 'writing PR description'
        top_k: 返回最相关的 N 个工作流模板
    """
    req = SearchRequest(
        user_id=user_id,
        query=trigger_context,
        types=[MemoryType.PROCEDURAL],
        top_k=top_k,
        score_threshold=0.45,
    )
    res = _run(
        orchestrator.search(
            user_id=req.user_id, query=req.query, types=req.types,
            top_k=req.top_k, score_threshold=req.score_threshold,
        )
    )
    data = res.model_dump(mode="json")
    # 抽出 structured.steps 给 Agent 直接用
    workflows = []
    for r in data.get("results", []):
        s = r["record"].get("structured", {})
        workflows.append({
            "task_pattern": s.get("task_pattern", r["record"]["content"][:60]),
            "steps": s.get("steps", []),
            "memory_id": r["record"]["id"],
            "score": r["signals"]["final_score"],
        })
    data["workflows"] = workflows
    return data


@mcp.tool()
def get_profile(user_id: str, auto_refresh: bool = False) -> dict[str, Any]:
    """获取用户画像 (Reflective Memory).

    Args:
        user_id: 用户标识
        auto_refresh: True 时若无缓存即时生成
    """
    return _run(orchestrator.get_profile(user_id, auto_refresh=auto_refresh))


@mcp.tool()
def track_signal(
    user_id: str,
    signal_type: str,
    context_tags: list[str] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """上报用户行为信号, 供 Pattern Miner 挖掘隐式偏好 (Phase 2).

    适用场景:
      - 用户要求重新生成 → signal_type='regenerate_request'
      - 用户明确纠正 → 'explicit_correction'
      - 用户改变格式偏好 → 'format_preference'
      - 用户选择了某 Tool 的结果 → 'tool_selection'
      - 用户表示满意 → 'positive_feedback'
      - 用户转换话题 → 'topic_pivot'

    Args:
        user_id: 用户标识
        signal_type: 6 种之一
        context_tags: 当时场景标签 (如 ['code_review', 'python'])
        session_id: 可选会话 ID
    """
    from app.pattern import track_signal as _track
    try:
        st = SignalType(signal_type.lower())
    except ValueError:
        return {"error": f"非法 signal_type: {signal_type}. 支持: "
                         f"{[s.value for s in SignalType]}"}
    sid = _run(_track(
        user_id=user_id, signal_type=st,
        context_tags=context_tags or [], session_id=session_id,
    ))
    return {"signal_id": sid, "status": "recorded"}


@mcp.tool()
def reflect(
    user_id: str,
    window_days: int = 14,
) -> dict[str, Any]:
    """分析最近行为信号, 触发 Pattern Miner 生成 Implicit Memory.

    建议在长对话结束时或用户明确要求时调用. 不需要频繁调用 (后台 Worker 每 30 min 自动跑).

    Args:
        user_id: 用户标识
        window_days: 分析最近 N 天的信号 (默认 14)
    """
    from app.pattern import mine_patterns_for_user
    new_records = _run(mine_patterns_for_user(user_id, window_days=window_days))
    return {
        "user_id": user_id,
        "window_days": window_days,
        "new_implicit_count": len(new_records),
        "new_records": [
            {
                "id": r.id,
                "content": r.content,
                "confidence": r.confidence_score,
                "keywords": r.structured.get("keywords", []),
                "evidence_count": r.structured.get("evidence_count"),
            }
            for r in new_records
        ],
    }


@mcp.tool()
def manage_memory(
    user_id: str,
    action: str,
    memory_id: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """查看、标记或删除特定记忆 (统一管理入口).

    Args:
        action: list / forget / mark_stale (合并 update/delete)
        memory_id: 操作单条记忆 ID; action=forget 且 memory_id=None 时清空全部
        confirm: forget 时必须为 True
    """
    if action == "list":
        meta = get_metadata()
        items = _run(meta.list_memories(user_id, limit=50))
        return {
            "user_id": user_id,
            "count": len(items),
            "items": [
                {"id": r.id, "type": r.type.value, "content": r.content[:200],
                 "confidence": r.confidence_score, "staleness": r.staleness_signal,
                 "created_at": r.created_at.isoformat()}
                for r in items
            ],
        }
    if action == "forget":
        if not confirm:
            return {"error": "forget 需要 confirm=True"}
        if memory_id:
            return _run(orchestrator.forget(user_id=user_id, memory_id=memory_id))
        return _run(orchestrator.forget(user_id=user_id, all_user_data=True))
    if action == "mark_stale":
        if not memory_id:
            return {"error": "mark_stale 需要 memory_id"}
        meta = get_metadata()
        rec = _run(meta.get_memory(memory_id))
        if not rec or rec.user_id != user_id:
            return {"error": "memory_id 不存在或不属于此 user"}
        rec.staleness_signal = True
        _run(meta.upsert_memory(rec))
        return {"status": "marked_stale", "memory_id": memory_id}
    return {"error": f"未知 action: {action}, 支持: list / forget / mark_stale"}


@mcp.tool()
def list_arbitrations(user_id: str, limit: int = 20) -> dict[str, Any]:
    """查询冲突仲裁审计日志 (调试 / 可解释性)."""
    meta = get_metadata()
    items = _run(meta.list_arbitrations(user_id, limit=limit))
    return {"user_id": user_id, "count": len(items), "items": items}


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                     MCP Resources (Agent SystemPrompt 注入)           ║
# ╚══════════════════════════════════════════════════════════════════════╝


@mcp.resource("memory://summary/{user_id}")
def resource_summary(user_id: str) -> str:
    """返回用户核心 Semantic 记忆的精简摘要 (< 500 tokens), 供 Agent SystemPrompt 注入."""
    meta = get_metadata()
    semantic_records = _run(meta.list_memories(
        user_id, memory_type=MemoryType.SEMANTIC.value, limit=20,
    ))
    if not semantic_records:
        return f"# {user_id} — 无 semantic 记忆"
    lines = [f"# {user_id} — 核心事实 ({len(semantic_records)} 条)"]
    for r in semantic_records:
        marker = " ⚠STALE" if r.staleness_signal else ""
        lines.append(f"- {r.content}{marker}")
    return "\n".join(lines)


@mcp.resource("memory://profile/{user_id}")
def resource_profile(user_id: str) -> str:
    """返回结构化用户画像 (Reflective Memory). Markdown 格式."""
    profile_data = _run(orchestrator.get_profile(user_id, auto_refresh=False))
    p = profile_data.get("profile", {})
    if not p:
        return f"# {user_id} — 无画像 (调 reflect_profile 触发生成)"
    lines = [
        f"# {user_id} 用户画像",
        f"**简介**: {p.get('one_liner', 'N/A')}",
        f"**偏好**: {', '.join(p.get('preferences', []))}",
        f"**禁忌**: {', '.join(p.get('constraints', []))}",
        f"**交互风格**: {p.get('interaction_style', 'N/A')}",
    ]
    return "\n\n".join(lines)


@mcp.resource("memory://workflows/{user_id}")
def resource_workflows(user_id: str) -> str:
    """返回所有 Procedural Memory 索引."""
    meta = get_metadata()
    workflows = _run(meta.list_memories(
        user_id, memory_type=MemoryType.PROCEDURAL.value, limit=50,
    ))
    if not workflows:
        return f"# {user_id} — 无工作流"
    lines = [f"# {user_id} 工作流索引 ({len(workflows)} 个)"]
    for r in workflows:
        s = r.structured or {}
        lines.append(f"\n## {s.get('task_pattern', r.content[:50])}")
        for i, step in enumerate(s.get("steps", []), 1):
            lines.append(f"  {i}. {step}")
    return "\n".join(lines)


if __name__ == "__main__":
    logger.info(f"MemoCortex MCP Server (Phase 4) 启动 → http://127.0.0.1:{config.mcp_port}/mcp")
    logger.info(f"  Tools: remember / recall / recall_workflow / get_profile / "
                f"track_signal / reflect / manage_memory / list_arbitrations")
    logger.info(f"  Resources: memory://summary|profile|workflows/{{user_id}}")
    mcp.run(transport="streamable-http", host="127.0.0.1", port=config.mcp_port, path="/mcp")
