"""单元测试: NetworkXGraph 基础 CRUD"""

from __future__ import annotations

import pytest

from app.models import Triple
from app.storage.nx_graph import NetworkXGraph


@pytest.mark.asyncio
async def test_add_and_find_triple(tmp_path):
    g = NetworkXGraph(root_dir=tmp_path / "graph")
    t = Triple(subject="user", predicate="lives_in", object="北京")
    await g.add_triple("u1", t)

    found = await g.find_triples("u1", subject="user", predicate="lives_in")
    assert len(found) == 1
    assert found[0].object == "北京"


@pytest.mark.asyncio
async def test_neighbors(tmp_path):
    g = NetworkXGraph(root_dir=tmp_path / "graph")
    await g.add_triple("u2", Triple(subject="user", predicate="works_at", object="公司"))
    await g.add_triple("u2", Triple(subject="user", predicate="lives_in", object="北京"))
    await g.add_triple("u2", Triple(subject="公司", predicate="located_in", object="北京"))

    nb = await g.neighbors("u2", "user", max_hops=2)
    assert "北京" in nb
    assert "公司" in nb


@pytest.mark.asyncio
async def test_delete_triple(tmp_path):
    g = NetworkXGraph(root_dir=tmp_path / "graph")
    t = Triple(subject="user", predicate="likes", object="火锅")
    await g.add_triple("u3", t)
    assert len(await g.find_triples("u3")) == 1

    ok = await g.delete_triple("u3", t.id)
    assert ok
    assert len(await g.find_triples("u3")) == 0


@pytest.mark.asyncio
async def test_persist_and_reload(tmp_path):
    """持久化后, 新实例应能从同目录恢复."""
    root = tmp_path / "graph"
    g1 = NetworkXGraph(root_dir=root)
    await g1.add_triple("u4", Triple(subject="user", predicate="likes", object="爬山"))
    await g1.persist()

    g2 = NetworkXGraph(root_dir=root)
    found = await g2.find_triples("u4")
    assert len(found) == 1
    assert found[0].object == "爬山"
