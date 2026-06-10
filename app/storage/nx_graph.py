"""NetworkX 实现 KnowledgeGraph Protocol

per-user 一个 MultiDiGraph 实例, JSON 持久化到 data/graph/{user_id}.json.

生产替换为 Neo4j: 改 add/find/neighbors 用 Cypher, 接口不变.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

import networkx as nx
from loguru import logger

from app.config import config
from app.models import Triple
from app.utils.metrics import metrics


def _safe_user_dir(user_id: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in user_id)


class NetworkXGraph:
    """KnowledgeGraph 的 NetworkX MVP 实现.

    内存图: nx.MultiDiGraph
      - 节点 = 实体名 (str)
      - 边 = (subject, object, key=triple_id, attrs={predicate, confidence, ...})

    持久化: data/graph/{user_id}.json (写入时增量保存)
    """

    def __init__(self, root_dir: Path | None = None) -> None:
        """root_dir 可注入便于测试; 默认走 config.graph_dir."""
        if root_dir is None:
            config.ensure_dirs()
            self._root = config.graph_dir
        else:
            self._root = root_dir
            self._root.mkdir(parents=True, exist_ok=True)
        self._graphs: dict[str, nx.MultiDiGraph] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = Lock()
        logger.info(f"NetworkXGraph 初始化 — dir={self._root}")

    # ── Persistence ────────────────────────────────────────────────────
    def _user_file(self, user_id: str) -> Path:
        return self._root / f"{_safe_user_dir(user_id)}.json"

    def _get_graph(self, user_id: str) -> nx.MultiDiGraph:
        """懒加载 + 缓存. 线程安全."""
        if user_id in self._graphs:
            return self._graphs[user_id]
        with self._global_lock:
            if user_id in self._graphs:
                return self._graphs[user_id]
            g: nx.MultiDiGraph = nx.MultiDiGraph()
            path = self._user_file(user_id)
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    g = nx.node_link_graph(data, multigraph=True, directed=True, edges="edges")
                except Exception as e:
                    logger.warning(f"加载图失败 ({path}): {e}, 用空图")
            self._graphs[user_id] = g
            return g

    def _get_lock(self, user_id: str) -> asyncio.Lock:
        with self._global_lock:
            if user_id not in self._locks:
                self._locks[user_id] = asyncio.Lock()
            return self._locks[user_id]

    async def _save_user(self, user_id: str) -> None:
        g = self._get_graph(user_id)
        path = self._user_file(user_id)
        try:
            data = nx.node_link_data(g, edges="edges")
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            os.replace(tmp, path)
        except Exception as e:
            logger.error(f"保存图失败 ({path}): {e}")

    # ── Write ──────────────────────────────────────────────────────────
    async def add_triple(self, user_id: str, triple: Triple) -> None:
        async with self._get_lock(user_id):
            g = self._get_graph(user_id)
            attrs = {
                "predicate": triple.predicate,
                "confidence": triple.confidence,
                "source_memory_id": triple.source_memory_id or "",
                "created_at": triple.created_at.isoformat(),
                "valid_from": triple.valid_from.isoformat() if triple.valid_from else "",
                "valid_until": triple.valid_until.isoformat() if triple.valid_until else "",
                "object": triple.object,
                "subject": triple.subject,
            }
            g.add_edge(triple.subject, triple.object, key=triple.id, **attrs)
            metrics.incr("graph.triples_added")
            await self._save_user(user_id)

    # ── Query ──────────────────────────────────────────────────────────
    async def find_triples(
        self,
        user_id: str,
        subject: str | None = None,
        predicate: str | None = None,
        obj: str | None = None,
    ) -> list[Triple]:
        g = self._get_graph(user_id)
        out: list[Triple] = []
        for u, v, key, data in g.edges(keys=True, data=True):
            if subject is not None and u != subject:
                continue
            if obj is not None and v != obj:
                continue
            if predicate is not None and data.get("predicate") != predicate:
                continue
            out.append(self._edge_to_triple(u, v, key, data))
        return out

    async def delete_triple(self, user_id: str, triple_id: str) -> bool:
        async with self._get_lock(user_id):
            g = self._get_graph(user_id)
            found_edge = None
            for u, v, key in g.edges(keys=True):
                if key == triple_id:
                    found_edge = (u, v, key)
                    break
            if not found_edge:
                return False
            g.remove_edge(*found_edge)
            await self._save_user(user_id)
            return True

    async def neighbors(
        self, user_id: str, entity: str, max_hops: int = 2
    ) -> set[str]:
        g = self._get_graph(user_id)
        if entity not in g:
            return set()
        # 无向 BFS, 距离 ≤ max_hops
        undirected = g.to_undirected(as_view=True)
        result: set[str] = set()
        try:
            lengths = nx.single_source_shortest_path_length(undirected, entity, cutoff=max_hops)
            for node, dist in lengths.items():
                if 0 < dist <= max_hops:
                    result.add(str(node))
        except Exception as e:
            logger.warning(f"neighbors BFS 失败: {e}")
        return result

    async def delete_by_user(self, user_id: str) -> int:
        async with self._get_lock(user_id):
            g = self._get_graph(user_id)
            count = g.number_of_edges()
            self._graphs.pop(user_id, None)
            path = self._user_file(user_id)
            if path.exists():
                path.unlink()
            logger.info(f"GDPR delete graph: user={user_id}, edges={count}")
            return count

    async def persist(self) -> None:
        """全量保存所有用户图 (lifespan shutdown 调用)."""
        for user_id in list(self._graphs.keys()):
            await self._save_user(user_id)

    # ── Helpers ────────────────────────────────────────────────────────
    @staticmethod
    def _edge_to_triple(u: str, v: str, key: str, data: dict[str, Any]) -> Triple:
        from datetime import datetime

        def _parse_ts(s: str | None) -> datetime | None:
            if not s:
                return None
            try:
                return datetime.fromisoformat(s)
            except ValueError:
                return None

        return Triple(
            id=key,
            subject=str(u),
            predicate=str(data.get("predicate", "")),
            object=str(v),
            confidence=float(data.get("confidence", 1.0)),
            source_memory_id=str(data.get("source_memory_id") or "") or None,
            created_at=_parse_ts(data.get("created_at")) or datetime.now(),
            valid_from=_parse_ts(data.get("valid_from")),
            valid_until=_parse_ts(data.get("valid_until")),
        )
