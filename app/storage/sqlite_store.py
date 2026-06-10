"""SQLAlchemy 2.0 + SQLite 异步实现 MetadataStore Protocol

4 张表:
  memories            — MemoryRecord 持久化备份 (真源)
  reflective_profiles — 用户画像 JSON Blob
  arbitration_logs    — 冲突仲裁审计
  eval_runs           — Eval 跑分历史 (跨版本回归对比)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import config
from app.models import MemoryRecord, MemoryType


class Base(DeclarativeBase):
    pass


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                          ORM Models                                  ║
# ╚══════════════════════════════════════════════════════════════════════╝


class MemoryORM(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True)
    session_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(20), index=True)
    content: Mapped[str] = mapped_column(Text)
    structured: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    last_recalled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recall_count: Mapped[int] = mapped_column(Integer, default=0)
    ttl_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tier: Mapped[str] = mapped_column(String(10), default="hot")
    storage_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tags: Mapped[str] = mapped_column(String(500), default="")  # CSV
    source: Mapped[str] = mapped_column(String(30), default="explicit")


class ReflectiveProfileORM(Base):
    __tablename__ = "reflective_profiles"

    user_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ArbitrationLogORM(Base):
    __tablename__ = "arbitration_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True)
    subject: Mapped[str] = mapped_column(String(200))
    predicate: Mapped[str] = mapped_column(String(100))
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(20))
    reasoning: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class EvalRunORM(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    suite: Mapped[str] = mapped_column(String(80), index=True)
    score: Mapped[float] = mapped_column(Float)
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                      Helpers: ORM ↔ Pydantic                         ║
# ╚══════════════════════════════════════════════════════════════════════╝


def _orm_to_record(o: MemoryORM) -> MemoryRecord:
    return MemoryRecord(
        id=o.id,
        user_id=o.user_id,
        session_id=o.session_id,
        type=MemoryType(o.type),
        content=o.content,
        structured=o.structured or {},
        importance=o.importance,
        created_at=o.created_at,
        last_recalled_at=o.last_recalled_at,
        recall_count=o.recall_count,
        ttl_at=o.ttl_at,
        tier=o.tier,
        storage_uri=o.storage_uri,
        tags=[t for t in (o.tags or "").split(",") if t],
        source=o.source,
    )


def _record_to_orm(r: MemoryRecord) -> MemoryORM:
    return MemoryORM(
        id=r.id,
        user_id=r.user_id,
        session_id=r.session_id,
        type=r.type.value,
        content=r.content,
        structured=r.structured,
        importance=r.importance,
        created_at=r.created_at,
        last_recalled_at=r.last_recalled_at,
        recall_count=r.recall_count,
        ttl_at=r.ttl_at,
        tier=r.tier,
        storage_uri=r.storage_uri,
        tags=",".join(r.tags),
        source=r.source,
    )


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                      SQLiteMetadataStore                             ║
# ╚══════════════════════════════════════════════════════════════════════╝


class SQLiteMetadataStore:
    """MetadataStore 的 SQLite 实现 (异步)."""

    def __init__(self) -> None:
        config.ensure_dirs()
        self._engine = create_async_engine(
            config.sqlite_url,
            echo=False,
            future=True,
        )
        self._sessionmaker = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        logger.info(f"SQLiteMetadataStore 初始化 — url={config.sqlite_url}")

    async def init_schema(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("SQLite schema 已就绪")

    # ── Memory ─────────────────────────────────────────────────────────
    async def upsert_memory(self, record: MemoryRecord) -> None:
        async with self._sessionmaker() as session:
            existing = await session.get(MemoryORM, record.id)
            if existing:
                for k, v in _record_to_orm(record).__dict__.items():
                    if k.startswith("_"):
                        continue
                    setattr(existing, k, v)
            else:
                session.add(_record_to_orm(record))
            await session.commit()

    async def get_memory(self, memory_id: str) -> MemoryRecord | None:
        async with self._sessionmaker() as session:
            orm = await session.get(MemoryORM, memory_id)
            return _orm_to_record(orm) if orm else None

    async def list_memories(
        self,
        user_id: str,
        memory_type: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        async with self._sessionmaker() as session:
            stmt = select(MemoryORM).where(MemoryORM.user_id == user_id)
            if memory_type:
                stmt = stmt.where(MemoryORM.type == memory_type)
            if since:
                stmt = stmt.where(MemoryORM.created_at >= since)
            stmt = stmt.order_by(MemoryORM.created_at.desc()).limit(limit)
            result = await session.execute(stmt)
            return [_orm_to_record(o) for o in result.scalars().all()]

    async def delete_memory(self, memory_id: str) -> bool:
        async with self._sessionmaker() as session:
            orm = await session.get(MemoryORM, memory_id)
            if not orm:
                return False
            await session.delete(orm)
            await session.commit()
            return True

    # ── Reflective Profile ─────────────────────────────────────────────
    async def upsert_profile(self, user_id: str, profile: dict[str, Any]) -> None:
        async with self._sessionmaker() as session:
            existing = await session.get(ReflectiveProfileORM, user_id)
            if existing:
                existing.profile = profile
                existing.updated_at = datetime.now()
            else:
                session.add(
                    ReflectiveProfileORM(
                        user_id=user_id, profile=profile, updated_at=datetime.now()
                    )
                )
            await session.commit()

    async def get_profile(self, user_id: str) -> dict[str, Any] | None:
        async with self._sessionmaker() as session:
            orm = await session.get(ReflectiveProfileORM, user_id)
            if not orm:
                return None
            return {"profile": orm.profile, "updated_at": orm.updated_at.isoformat()}

    # ── Arbitration ────────────────────────────────────────────────────
    async def log_arbitration(self, entry: dict[str, Any]) -> None:
        async with self._sessionmaker() as session:
            session.add(
                ArbitrationLogORM(
                    user_id=entry["user_id"],
                    subject=entry["subject"],
                    predicate=entry["predicate"],
                    old_value=entry.get("old_value"),
                    new_value=entry["new_value"],
                    action=entry["action"],
                    reasoning=entry.get("reasoning", ""),
                    confidence=float(entry.get("confidence", 1.0)),
                )
            )
            await session.commit()

    async def list_arbitrations(
        self, user_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        async with self._sessionmaker() as session:
            stmt = (
                select(ArbitrationLogORM)
                .where(ArbitrationLogORM.user_id == user_id)
                .order_by(ArbitrationLogORM.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [
                {
                    "id": o.id,
                    "user_id": o.user_id,
                    "subject": o.subject,
                    "predicate": o.predicate,
                    "old_value": o.old_value,
                    "new_value": o.new_value,
                    "action": o.action,
                    "reasoning": o.reasoning,
                    "confidence": o.confidence,
                    "created_at": o.created_at.isoformat(),
                }
                for o in result.scalars().all()
            ]

    # ── Eval ───────────────────────────────────────────────────────────
    async def save_eval_run(
        self, suite: str, score: float, details: dict[str, Any]
    ) -> None:
        async with self._sessionmaker() as session:
            session.add(EvalRunORM(suite=suite, score=score, details=details))
            await session.commit()

    async def last_eval(self, suite: str) -> dict[str, Any] | None:
        async with self._sessionmaker() as session:
            stmt = (
                select(EvalRunORM)
                .where(EvalRunORM.suite == suite)
                .order_by(EvalRunORM.created_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            orm = result.scalars().first()
            if not orm:
                return None
            return {
                "suite": orm.suite,
                "score": orm.score,
                "details": orm.details,
                "created_at": orm.created_at.isoformat(),
            }

    async def list_eval_runs(self, suite: str, limit: int = 20) -> list[dict[str, Any]]:
        """查询某 suite 的历史跑分 (按时间倒序)."""
        async with self._sessionmaker() as session:
            stmt = (
                select(EvalRunORM)
                .where(EvalRunORM.suite == suite)
                .order_by(EvalRunORM.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [
                {
                    "suite": o.suite,
                    "score": o.score,
                    "details": o.details,
                    "created_at": o.created_at.isoformat(),
                }
                for o in result.scalars().all()
            ]
