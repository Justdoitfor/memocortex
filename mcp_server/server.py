"""MemoCortex MCP Server — 用 fastmcp 暴露 4 个工具给任意 MCP 客户端

工具:
  - memory_write
  - memory_search
  - memory_get_profile
  - memory_forget

启动:
  uv run python -m mcp_server.server
  → http://127.0.0.1:8766/mcp

接入 Claude Desktop / Cursor / Cline 等 MCP 客户端即可让 LLM 自主调用记忆.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastmcp import FastMCP
from loguru import logger

from app.config import config
from app.models import (
    ForgetRequest,
    MemoryType,
    SearchRequest,
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


@mcp.tool()
def memory_write(
    user_id: str,
    content: str,
    memory_type: str = "episodic",
    session_id: str | None = None,
    importance: float | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """写入一条记忆.

    Args:
        user_id: 用户标识 (必须)
        content: 自然语言文本
        memory_type: working / episodic / semantic / procedural (默认 episodic)
        session_id: 会话 ID (working / 短期上下文场景)
        importance: 0-1 重要度, None 自动 0.5
        tags: 自定义标签
    """
    try:
        mtype = MemoryType(memory_type.lower())
    except ValueError:
        return {"error": f"非法 memory_type: {memory_type}"}

    req = WriteRequest(
        user_id=user_id,
        content=content,
        type=mtype,
        session_id=session_id,
        importance=importance,
        tags=tags or [],
    )
    res = _run(orchestrator.write(req))
    return res.model_dump(mode="json")


@mcp.tool()
def memory_search(
    user_id: str,
    query: str,
    types: list[str] | None = None,
    top_k: int = 8,
    session_id: str | None = None,
) -> dict[str, Any]:
    """混合召回相关记忆 (4 信号融合).

    Args:
        user_id: 用户标识
        query: 召回查询语句
        types: 限定记忆类型列表 (None = 全类型)
        top_k: 返回条数
        session_id: 若提供, working memory 强优先
    """
    parsed_types: list[MemoryType] | None = None
    if types:
        try:
            parsed_types = [MemoryType(t.lower()) for t in types]
        except ValueError as e:
            return {"error": str(e)}

    req = SearchRequest(
        user_id=user_id,
        query=query,
        types=parsed_types,
        top_k=top_k,
        session_id=session_id,
    )
    res = _run(
        orchestrator.search(
            user_id=req.user_id,
            query=req.query,
            types=req.types,
            top_k=req.top_k,
            session_id=req.session_id,
        )
    )
    return res.model_dump(mode="json")


@mcp.tool()
def memory_get_profile(user_id: str, auto_refresh: bool = False) -> dict[str, Any]:
    """获取用户画像 (Reflective Memory).

    Args:
        user_id: 用户标识
        auto_refresh: True 时若无缓存即时生成
    """
    return _run(orchestrator.get_profile(user_id, auto_refresh=auto_refresh))


@mcp.tool()
def memory_forget(
    user_id: str,
    memory_id: str | None = None,
    confirm: bool = False,
    all_user_data: bool = False,
) -> dict[str, Any]:
    """删除记忆 (GDPR 合规).

    Args:
        user_id: 用户标识
        memory_id: 指定 ID 删除单条
        confirm: 必须为 True 才会执行 (二次确认)
        all_user_data: True 时级联清空该用户的全部记忆
    """
    if not confirm:
        return {"error": "需要 confirm=True 才能删除"}
    if all_user_data:
        return _run(orchestrator.forget(user_id=user_id, all_user_data=True))
    if memory_id:
        return _run(orchestrator.forget(user_id=user_id, memory_id=memory_id))
    return {"error": "需要 memory_id 或 all_user_data=True"}


@mcp.tool()
def memory_list_arbitrations(user_id: str, limit: int = 20) -> dict[str, Any]:
    """查询冲突仲裁审计日志 (调试 / 可解释性)."""
    meta = get_metadata()
    items = _run(meta.list_arbitrations(user_id, limit=limit))
    return {"user_id": user_id, "count": len(items), "items": items}


if __name__ == "__main__":
    logger.info(f"MemoCortex MCP Server 启动 → http://127.0.0.1:{config.mcp_port}/mcp")
    mcp.run(transport="streamable-http", host="127.0.0.1", port=config.mcp_port, path="/mcp")
