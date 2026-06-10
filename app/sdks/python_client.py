"""MemoCortex Python SDK — 同步 + 异步双 Client

让任何 Python Agent 项目 5 行代码接入:

    from app.sdks.python_client import MemoCortexClient
    client = MemoCortexClient(base_url="http://localhost:8765")
    client.write(user_id="alice", content="我对花生过敏")
    results = client.search(user_id="alice", query="过敏原")
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models import MemoryType


def _retry():
    """通用重试装饰器: 指数退避 3 次."""
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )


class MemoCortexClient:
    """同步 Client (面向脚本和 demo)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8765",
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base_url, timeout=timeout)

    @_retry()
    def write(
        self,
        user_id: str,
        content: str,
        type: MemoryType | str = MemoryType.EPISODIC,
        session_id: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
        structured: dict[str, Any] | None = None,
    ) -> dict:
        body = {
            "user_id": user_id,
            "content": content,
            "type": type.value if isinstance(type, MemoryType) else type,
            "session_id": session_id,
            "importance": importance,
            "tags": tags or [],
            "structured": structured or {},
        }
        r = self._client.post("/v1/memories", json=body)
        r.raise_for_status()
        return r.json()

    @_retry()
    def search(
        self,
        user_id: str,
        query: str,
        types: list[MemoryType | str] | None = None,
        top_k: int = 8,
        session_id: str | None = None,
    ) -> dict:
        body = {
            "user_id": user_id,
            "query": query,
            "types": [t.value if isinstance(t, MemoryType) else t for t in types]
            if types
            else None,
            "top_k": top_k,
            "session_id": session_id,
        }
        r = self._client.post("/v1/memories/search", json=body)
        r.raise_for_status()
        return r.json()

    @_retry()
    def get_profile(self, user_id: str, auto_refresh: bool = False) -> dict:
        r = self._client.get(
            f"/v1/users/{user_id}/profile", params={"auto_refresh": auto_refresh}
        )
        r.raise_for_status()
        return r.json()

    @_retry()
    def get_entity(self, user_id: str, entity: str, predicate: str | None = None) -> dict:
        params = {"predicate": predicate} if predicate else {}
        r = self._client.get(f"/v1/users/{user_id}/entities/{entity}", params=params)
        r.raise_for_status()
        return r.json()

    @_retry()
    def forget(
        self,
        user_id: str,
        memory_id: str | None = None,
        confirm: bool = False,
    ) -> dict:
        body = {"user_id": user_id, "memory_id": memory_id, "confirm": confirm}
        r = self._client.post("/v1/memories/forget", json=body)
        r.raise_for_status()
        return r.json()

    def reflect(self, user_id: str) -> dict:
        r = self._client.post(f"/admin/reflect/{user_id}")
        r.raise_for_status()
        return r.json()

    def list_arbitrations(self, user_id: str, limit: int = 50) -> dict:
        r = self._client.get(
            f"/admin/arbitrations/{user_id}", params={"limit": limit}
        )
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> MemoCortexClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class AsyncMemoCortexClient:
    """异步 Client (面向 FastAPI / 异步 Agent 框架)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8765",
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    async def write(
        self,
        user_id: str,
        content: str,
        type: MemoryType | str = MemoryType.EPISODIC,
        session_id: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
        structured: dict[str, Any] | None = None,
    ) -> dict:
        body = {
            "user_id": user_id,
            "content": content,
            "type": type.value if isinstance(type, MemoryType) else type,
            "session_id": session_id,
            "importance": importance,
            "tags": tags or [],
            "structured": structured or {},
        }
        r = await self._client.post("/v1/memories", json=body)
        r.raise_for_status()
        return r.json()

    async def search(
        self,
        user_id: str,
        query: str,
        types: list[MemoryType | str] | None = None,
        top_k: int = 8,
        session_id: str | None = None,
    ) -> dict:
        body = {
            "user_id": user_id,
            "query": query,
            "types": [t.value if isinstance(t, MemoryType) else t for t in types]
            if types
            else None,
            "top_k": top_k,
            "session_id": session_id,
        }
        r = await self._client.post("/v1/memories/search", json=body)
        r.raise_for_status()
        return r.json()

    async def get_profile(self, user_id: str, auto_refresh: bool = False) -> dict:
        r = await self._client.get(
            f"/v1/users/{user_id}/profile", params={"auto_refresh": auto_refresh}
        )
        r.raise_for_status()
        return r.json()

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncMemoCortexClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
