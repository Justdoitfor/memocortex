"""Reflection Workers — APScheduler 周期任务

4 个任务:
  1. distill_episodic_to_semantic   — Episodic → Semantic 提炼
  2. merge_duplicates              — 相似 Semantic 三元组合并 (MVP 简化)
  3. decay_importance              — 长期未召回的记忆 importance 衰减
  4. refresh_reflective_profile    — 重新生成用户画像

API 入口 (/admin/reflect/{user_id}) 可手动触发 (绕过 scheduler).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from app.config import config
from app.memories.reflective import reflective_memory
from app.memories.semantic import semantic_memory
from app.models import MemoryType
from app.storage import get_metadata, get_vector_store
from app.utils.metrics import metrics

_scheduler: AsyncIOScheduler | None = None


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                         Task 1: Distillation                         ║
# ╚══════════════════════════════════════════════════════════════════════╝


async def distill_episodic_to_semantic(user_id: str | None = None) -> dict[str, Any]:
    """从最近 N 天 Episodic 中, LLM 提炼出可结构化的事实写入 Semantic.

    MVP 简化: 这一动作已经在 Orchestrator.write() 里 fire-and-forget 做了,
    这里只做"补偿性"——挑出没被抽取过的旧 episodic 重新尝试.
    """
    meta = get_metadata()
    since = datetime.now() - timedelta(days=7)

    # 这里 user_id=None 时简化为"不做全表扫", 实际场景应分页扫所有用户
    if user_id is None:
        return {"skipped": True, "reason": "MVP: distill 需指定 user_id"}

    records = await meta.list_memories(
        user_id, memory_type=MemoryType.EPISODIC.value, since=since, limit=50
    )
    processed = 0
    for r in records:
        # 只补偿没被抽取过的 (source != distilled)
        if r.source == "distilled":
            continue
        try:
            await semantic_memory.write_from_text(
                user_id=user_id, text=r.content, source_memory_id=r.id
            )
            processed += 1
        except Exception as e:
            logger.warning(f"distill 失败 {r.id}: {e}")
    logger.info(f"[Reflection] distill: user={user_id} processed={processed}/{len(records)}")
    metrics.incr("reflection.distill.runs")
    return {"user_id": user_id, "scanned": len(records), "distilled": processed}


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                         Task 2: Merge Duplicates                     ║
# ╚══════════════════════════════════════════════════════════════════════╝


async def merge_duplicates(user_id: str | None = None) -> dict[str, Any]:
    """查找近似重复的 Semantic 三元组并合并.

    MVP 实现: 直接基于 KG 中相同 (subject, predicate, object) 的 triple,
    Chroma 端按内容哈希 (相同 content) 留最高 importance 的一个.
    """
    if user_id is None:
        return {"skipped": True, "reason": "MVP: merge 需指定 user_id"}

    meta = get_metadata()
    records = await meta.list_memories(
        user_id, memory_type=MemoryType.SEMANTIC.value, limit=500
    )
    # 按 content 分桶
    buckets: dict[str, list] = {}
    for r in records:
        buckets.setdefault(r.content, []).append(r)

    removed = 0
    vec = get_vector_store()
    for _content, group in buckets.items():
        if len(group) <= 1:
            continue
        # 留 importance 最高 + recall_count 最多的, 其他删除
        keep = max(group, key=lambda r: (r.importance, r.recall_count))
        for r in group:
            if r.id == keep.id:
                continue
            try:
                await vec.delete(r.id, user_id)
                await meta.delete_memory(r.id)
                removed += 1
            except Exception as e:
                logger.warning(f"merge 删除失败 {r.id}: {e}")

    logger.info(f"[Reflection] merge_duplicates: user={user_id} removed={removed}")
    metrics.incr("reflection.merge.runs")
    return {"user_id": user_id, "scanned": len(records), "removed": removed}


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                         Task 3: Importance Decay                     ║
# ╚══════════════════════════════════════════════════════════════════════╝


async def decay_importance(user_id: str | None = None) -> dict[str, Any]:
    """对长期未召回的记忆做 importance 指数衰减, 低于阈值标记为冷数据."""
    if user_id is None:
        return {"skipped": True, "reason": "MVP: decay 需指定 user_id"}

    meta = get_metadata()
    vec = get_vector_store()
    now = datetime.now()
    records = await meta.list_memories(user_id, limit=1000)
    decayed = 0
    cooled = 0
    for r in records:
        last = r.last_recalled_at or r.created_at
        days_silent = (now - last).total_seconds() / 86400.0
        # 60 天未召回 → 半衰一次
        new_imp = r.importance * math.exp(-days_silent / 120.0)
        if abs(new_imp - r.importance) < 0.01:
            continue
        r.importance = round(new_imp, 4)
        try:
            await vec.update_metadata(r.id, user_id, {"importance": r.importance})
            await meta.upsert_memory(r)
            decayed += 1
            # importance < 0.1 且 30 天未召回 → 标 cold
            if r.importance < 0.1 and days_silent > 30 and r.tier == "hot":
                r.tier = "cold"
                await meta.upsert_memory(r)
                cooled += 1
        except Exception as e:
            logger.warning(f"decay 更新失败 {r.id}: {e}")

    logger.info(f"[Reflection] decay: user={user_id} decayed={decayed} cooled={cooled}")
    metrics.incr("reflection.decay.runs")
    return {"user_id": user_id, "decayed": decayed, "cooled": cooled}


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                         Task 4: Profile Refresh                      ║
# ╚══════════════════════════════════════════════════════════════════════╝


async def refresh_reflective_profile(user_id: str) -> dict[str, Any]:
    """重新生成用户画像."""
    profile = await reflective_memory.refresh(user_id)
    return {"user_id": user_id, "profile": profile}


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                         Scheduler 控制                                ║
# ╚══════════════════════════════════════════════════════════════════════╝


def start_scheduler() -> AsyncIOScheduler:
    """启动调度器 (lifespan 调用).

    注意: MVP 阶段后台任务不指定 user_id, 会被任务内 'skipped' 路径捕获.
    生产应用应在 Orchestrator 写入时把活跃 user_id 入队, scheduler 消费.
    """
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = AsyncIOScheduler()
    # MVP: 间隔从 config 读, demo 时可调短
    _scheduler.add_job(
        lambda: distill_episodic_to_semantic(None),
        "interval",
        seconds=config.reflect_distill_interval_sec,
        id="distill",
    )
    _scheduler.add_job(
        lambda: merge_duplicates(None),
        "interval",
        seconds=config.reflect_merge_interval_sec,
        id="merge",
    )
    _scheduler.add_job(
        lambda: decay_importance(None),
        "interval",
        seconds=config.reflect_decay_interval_sec,
        id="decay",
    )
    _scheduler.start()
    logger.info(
        f"Reflection scheduler 启动: distill={config.reflect_distill_interval_sec}s "
        f"merge={config.reflect_merge_interval_sec}s decay={config.reflect_decay_interval_sec}s"
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Reflection scheduler 已停止")


async def run_all_for_user(user_id: str) -> dict[str, Any]:
    """便捷入口: 给定 user_id, 跑全套 4 个任务 (供 /admin/reflect API 调用)."""
    return {
        "distill": await distill_episodic_to_semantic(user_id),
        "merge": await merge_duplicates(user_id),
        "decay": await decay_importance(user_id),
        "profile": await refresh_reflective_profile(user_id),
    }
