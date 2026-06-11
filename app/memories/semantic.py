"""Semantic Memory — 事实知识 (用户偏好/属性, 三元组)

双索引设计:
  - NetworkX 知识图谱: (subject, predicate, object) triple → BFS/Cypher 风格查询
  - ChromaDB 向量库: 自然语言原文 → 语义召回 (兜底召回)

核心流程 (write):
  1. LLM Entity Extractor: 自然语言 → List[Triple]
  2. 对每个 triple, 查 KG 是否已有 (subject, predicate, *) → 检测冲突
  3. 有冲突 → 调 Arbitrator 决策 (REPLACE/MERGE/VERSIONED/IGNORE)
  4. 按决策应用到 KG + 双写 ChromaDB
  5. 全程日志到 arbitration_logs

冲突 Arbitrator 在 Phase 3 实现, 这里先实现 Entity Extractor + KG 同步.
"""

from __future__ import annotations

from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from loguru import logger
from pydantic import BaseModel, Field

from app.core.llm_factory import llm_factory
from app.models import MemoryRecord, MemoryType, Triple
from app.storage import get_kg, get_metadata, get_vector_store
from app.utils.metrics import metrics

# ╔══════════════════════════════════════════════════════════════════════╗
# ║                       LLM Entity Extractor                           ║
# ╚══════════════════════════════════════════════════════════════════════╝


class _ExtractedTriple(BaseModel):
    """LLM 输出的单个 triple (内部用)."""

    subject: str = Field(description="实体名, 用户相关事实通常是 'user'")
    predicate: str = Field(description="谓词, 小写下划线, e.g. lives_in / allergic_to / likes")
    object: str = Field(description="值, 实体名/字面值")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class _ExtractResult(BaseModel):
    """LLM 输出的完整结构: 多个 triples."""

    triples: list[_ExtractedTriple] = Field(default_factory=list)


_EXTRACT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "你是一个事实抽取器. 把用户对话中的客观事实抽取为 (subject, predicate, object) 三元组.\n"
                "\n"
                "规则:\n"
                "- subject: 与用户相关的事实统一用 'user'\n"
                "- predicate: 必须小写下划线英文. 常用 predicate 列表 (优先复用):\n"
                "  * 基本属性: age / occupation / gender / married_to / weight_kg / height_cm\n"
                "  * 地理: lives_in / works_at / hometown / visited\n"
                "  * 关系: has_pet / has_child / girlfriend / boyfriend / spouse / sibling\n"
                "  * 偏好: likes / dislikes / favorite_food / favorite_color / hobby\n"
                "  * 健康: allergic_to / blood_type\n"
                "  * 物品: owns_car / owns_phone / owns_laptop / uses_camera\n"
                "  * 能力: speaks_language / educational_background\n"
                "  * 未在列表中的概念也可以新建 predicate, 保持英文小写下划线即可\n"
                "- object: 实体名或字面值 (单位用统一格式, e.g. '70 公斤' / 'iPhone 16 Pro')\n"
                "- 只抽取明确的事实, 不抽取猜测/疑问/否定句\n"
                "- 时间相关 (e.g. '我以前住上海') 不抽取, 只抽取当前状态\n"
                "- 同一句话可能产出多个三元组\n"
                "- 如果没有可抽取的事实, 返回空 triples 列表\n"
                "\n"
                "示例:\n"
                "  '我对花生过敏'              → [(user, allergic_to, 花生)]\n"
                "  '我搬家了, 现在住北京'       → [(user, lives_in, 北京)]\n"
                "  '我家有只叫小白的猫'         → [(user, has_pet, 小白)]\n"
                "  '我会说中文和英语'           → [(user, speaks_language, 中文), (user, speaks_language, 英语)]\n"
                "  '我女朋友叫小雪'            → [(user, girlfriend, 小雪)]\n"
                "  '我的车是大众朗逸'           → [(user, owns_car, 大众朗逸)]\n"
                "  '我手机是 iPhone 14'        → [(user, owns_phone, iPhone 14)]\n"
                "  '我体重 80 公斤'            → [(user, weight_kg, 80)]\n"
                "  '我跳槽到字节做基础架构'      → [(user, works_at, 字节), (user, occupation, 基础架构)]\n"
                "  '今天天气真好'              → []  (无可结构化事实)\n"
                "\n"
                "返回 JSON, 格式: "
                '{{"triples": [{{"subject": "user", "predicate": "lives_in", "object": "北京", "confidence": 0.95}}]}}'
            ),
        ),
        ("human", "{text}"),
    ]
)


async def extract_triples(text: str) -> list[Triple]:
    """从自然语言抽取三元组列表. LLM 失败时返回空列表 (降级)."""
    try:
        with metrics.timer("semantic.extract.latency"):
            result = await llm_factory.structured_invoke(
                _EXTRACT_PROMPT, _ExtractResult, {"text": text}, temperature=0
            )
        if result is None:
            return []
        triples = [
            Triple(
                subject=t.subject.strip(),
                predicate=t.predicate.strip().lower(),
                object=t.object.strip(),
                confidence=t.confidence,
            )
            for t in result.triples
            if t.subject and t.predicate and t.object
        ]
        metrics.incr("semantic.triples_extracted", len(triples))
        return triples
    except Exception as e:
        logger.warning(f"Entity extraction 失败 (降级返回空): {e}")
        return []


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                       Field Semantics Schema                         ║
# ╚══════════════════════════════════════════════════════════════════════╝


# 字段语义: 决定冲突时默认 action
# - unique: 同 (subject, predicate) 只能有一个 object → 倾向 REPLACE
# - list:   可以有多个 object → 倾向 MERGE
# - versioned: 时间相关, 保留历史 → 倾向 VERSIONED
_FIELD_SCHEMA: dict[str, str] = {
    # unique (单值)
    "lives_in": "unique",
    "works_at": "unique",
    "age": "unique",
    "occupation": "unique",
    "married_to": "unique",
    "favorite_food": "unique",
    "favorite_color": "unique",
    "hometown": "unique",
    "weight_kg": "unique",
    "height_cm": "unique",
    "blood_type": "unique",
    "girlfriend": "unique",
    "boyfriend": "unique",
    "spouse": "unique",
    "owns_car": "unique",
    "owns_phone": "unique",
    "owns_laptop": "unique",
    "uses_camera": "unique",
    "educational_background": "unique",
    # list (多值)
    "allergic_to": "list",
    "likes": "list",
    "dislikes": "list",
    "has_pet": "list",
    "has_child": "list",
    "sibling": "list",
    "hobby": "list",
    "speaks_language": "list",
    "visited": "list",
}


def get_field_semantics(predicate: str) -> str:
    """返回 'unique' / 'list' / 'versioned', 未知谓词默认 'unique'."""
    return _FIELD_SCHEMA.get(predicate, "unique")


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                       Semantic Memory 主类                            ║
# ╚══════════════════════════════════════════════════════════════════════╝


class SemanticMemory:
    """事实知识记忆 — 双索引 (KG + Vector).

    Note: 冲突仲裁逻辑在 Phase 3 的 arbitrator 模块, 这里通过 hook 接口注入.
    """

    def __init__(self) -> None:
        self._kg = get_kg()
        self._vector = get_vector_store()
        self._meta = get_metadata()
        # arbitrator 在 Phase 3 注入, 这里先用 None 占位
        self._arbitrator = None
        logger.info("SemanticMemory 初始化")

    def set_arbitrator(self, arbitrator: Any) -> None:
        """由 orchestrator 在启动时注入 ConflictArbitrator 实例 (避免循环依赖)."""
        self._arbitrator = arbitrator

    async def write_from_text(
        self,
        user_id: str,
        text: str,
        source_memory_id: str | None = None,
        conflict_strategy: str = "arbitrator",
    ) -> list[dict[str, Any]]:
        """从自然语言抽取 + 写入. 返回每个 triple 的写入结果 (含 arbitration 决策).

        Args:
            conflict_strategy: arbitrator (LLM 决策, 默认) / staleness (软废弃) / auto

        每个返回元素结构:
          {
            "triple": Triple,
            "action": "added" | "replaced" | "merged" | "versioned" | "ignored" | "stale_marked",
            "arbitration": ArbitrationDecision | None,
          }
        """
        triples = await extract_triples(text)
        if not triples:
            return []

        results: list[dict[str, Any]] = []
        for triple in triples:
            triple.source_memory_id = source_memory_id
            res = await self.upsert_triple(user_id, triple, conflict_strategy=conflict_strategy)
            results.append(res)
        return results

    async def upsert_triple(
        self,
        user_id: str,
        triple: Triple,
        conflict_strategy: str = "arbitrator",
    ) -> dict[str, Any]:
        """写入单个 triple, 触发冲突检测 + 仲裁.

        Args:
            conflict_strategy:
                arbitrator (默认) — LLM 决策 REPLACE/MERGE/VERSIONED/IGNORE
                staleness — 直接软废弃旧 triple (跳过 LLM, 适合无 Key / 批量写)
                auto — LLM 失败时自动 fallback 到 staleness
        """
        # 检查冲突: 同 (subject, predicate) 已有 triple?
        existing = await self._kg.find_triples(
            user_id, subject=triple.subject, predicate=triple.predicate
        )
        existing = [t for t in existing if t.id != triple.id]  # 排除自身

        if not existing:
            # 无冲突, 直接添加
            await self._kg.add_triple(user_id, triple)
            await self._mirror_to_vector(user_id, triple)
            return {"triple": triple, "action": "added", "arbitration": None}

        # 已有相同 object → 幂等, 不重复添加
        for t in existing:
            if t.object == triple.object:
                logger.debug(f"Semantic upsert: 重复事实, 忽略 ({triple})")
                return {"triple": triple, "action": "duplicate", "arbitration": None}

        # ── Phase 1: 业务方显式选 staleness 策略 → 跳过 LLM, 直接软废弃 ──
        if conflict_strategy == "staleness":
            return await self._apply_staleness(user_id, triple, existing)

        # 有冲突 → 调 Arbitrator
        if self._arbitrator is None:
            # 降级: 没注入 arbitrator 时用字段语义启发式
            semantics = get_field_semantics(triple.predicate)
            if semantics == "list":
                await self._kg.add_triple(user_id, triple)
                await self._mirror_to_vector(user_id, triple)
                return {"triple": triple, "action": "merged_heuristic", "arbitration": None}
            else:
                # unique → 替换 (或软废弃)
                if conflict_strategy == "auto":
                    return await self._apply_staleness(user_id, triple, existing)
                for t in existing:
                    await self._kg.delete_triple(user_id, t.id)
                await self._kg.add_triple(user_id, triple)
                await self._mirror_to_vector(user_id, triple)
                return {"triple": triple, "action": "replaced_heuristic", "arbitration": None}

        # 走 Arbitrator
        try:
            decision = await self._arbitrator.arbitrate(
                user_id=user_id,
                new_triple=triple,
                existing_triples=existing,
                field_semantics=get_field_semantics(triple.predicate),
            )
            action_str = await self._apply_decision(user_id, triple, existing, decision)
            return {"triple": triple, "action": action_str, "arbitration": decision}
        except Exception as e:
            logger.warning(f"Arbitrator 失败 ({e}), conflict_strategy={conflict_strategy}")
            if conflict_strategy == "auto":
                return await self._apply_staleness(user_id, triple, existing)
            raise

    async def _apply_staleness(
        self,
        user_id: str,
        new_triple: Triple,
        existing: list[Triple],
    ) -> dict[str, Any]:
        """Staleness 路径: 旧 triple 不删, 但标 staleness → effective_strength × 0.2.

        新 triple 正常入库. 旧 episodic 不动 (审计可追溯).
        """
        from datetime import datetime

        from app.lifecycle.staleness import apply_staleness

        # 1. 新 triple 添加到 KG + 镜像 Chroma
        await self._kg.add_triple(user_id, new_triple)
        await self._mirror_to_vector(user_id, new_triple)

        # 2. 把所有旧 triple 关联的 source memory 一起软废弃
        meta = get_metadata()
        old_records: list[MemoryRecord] = []
        for old_t in existing:
            if not old_t.source_memory_id:
                continue
            old_rec = await meta.get_memory(old_t.source_memory_id)
            if old_rec:
                old_records.append(old_rec)

        # 3. 同时给旧 triple 自己 ("镜像在 Chroma 的 triple-mirror") 也降权
        #    旧 KG triple 不直接删除, 只在 Chroma metadata 标 staleness
        from app.storage import get_vector_store
        vec = get_vector_store()
        for old_t in existing:
            try:
                await vec.update_metadata(
                    old_t.id, user_id,
                    {"staleness_signal": 1, "superseded_by": new_triple.id},
                )
            except Exception:
                pass

        # 4. 创建新的 source record (CORRECTED 来源) 并软废弃旧 episodic
        new_record = MemoryRecord(
            id=new_triple.id,
            user_id=user_id,
            type=MemoryType.SEMANTIC,
            content=f"{new_triple.subject} {new_triple.predicate} {new_triple.object}",
            source_type="corrected",
            confidence_score=0.85,
            created_at=datetime.now(),
        )
        result = await apply_staleness(new_record, old_records)
        logger.info(
            f"[Staleness] Semantic 软废弃: 新 {new_triple.object}, 旧软废弃 "
            f"{len(result['superseded'])} 条 source memory"
        )

        return {
            "triple": new_triple,
            "action": "stale_marked",
            "arbitration": None,
            "superseded": result["superseded"],
        }

    async def _apply_decision(
        self,
        user_id: str,
        new_triple: Triple,
        existing: list[Triple],
        decision: Any,  # ArbitrationDecision, 避免循环依赖用 Any
    ) -> str:
        """执行 Arbitrator 决策."""
        from app.models import ConflictAction

        action = decision.action if hasattr(decision, "action") else ConflictAction(decision["action"])

        if action == ConflictAction.REPLACE:
            # 收集旧 triple 关联的 episodic source, 一起降权 (避免被 hybrid 召回顶上)
            stale_episodic_ids: set[str] = set()
            for t in existing:
                if t.source_memory_id:
                    stale_episodic_ids.add(t.source_memory_id)
                await self._kg.delete_triple(user_id, t.id)
                # 同时删除 Chroma 中的旧 mirror, 避免召回时混入过时事实
                await self._vector.delete(t.id, user_id)
            # 把对应的 Episodic 原文 importance 打到 0.05 (近似遗忘)
            for ep_id in stale_episodic_ids:
                try:
                    await self._vector.update_metadata(
                        ep_id, user_id, {"importance": 0.05, "tier": "cold"}
                    )
                except Exception:
                    pass
            await self._kg.add_triple(user_id, new_triple)
            await self._mirror_to_vector(user_id, new_triple)
            return "replaced"

        if action == ConflictAction.MERGE:
            # list 字段, 直接 append
            await self._kg.add_triple(user_id, new_triple)
            await self._mirror_to_vector(user_id, new_triple)
            return "merged"

        if action == ConflictAction.VERSIONED:
            from datetime import datetime

            now = datetime.now()
            # 旧 triple 设 valid_until = now
            for t in existing:
                t.valid_until = now
                await self._kg.delete_triple(user_id, t.id)
                await self._kg.add_triple(user_id, t)
            new_triple.valid_from = now
            await self._kg.add_triple(user_id, new_triple)
            await self._mirror_to_vector(user_id, new_triple)
            return "versioned"

        # IGNORE
        logger.info(f"Arbitrator 决定 IGNORE: {new_triple}")
        return "ignored"

    async def _mirror_to_vector(self, user_id: str, triple: Triple) -> None:
        """把 triple 同步到 ChromaDB 作为兜底语义召回."""
        text = f"{triple.subject} {triple.predicate} {triple.object}"
        record = MemoryRecord(
            id=triple.id,  # 用 triple id 关联
            user_id=user_id,
            type=MemoryType.SEMANTIC,
            content=text,
            structured={
                "subject": triple.subject,
                "predicate": triple.predicate,
                "object": triple.object,
                "confidence": triple.confidence,
            },
            importance=0.7,  # semantic 默认高重要度
            source="distilled" if triple.source_memory_id else "explicit",
        )
        await self._vector.add(record)
        await self._meta.upsert_memory(record)

    # ── Query ──────────────────────────────────────────────────────────
    async def query_entity(
        self, user_id: str, subject: str = "user", predicate: str | None = None
    ) -> list[Triple]:
        """直接查 KG: e.g. user 的所有事实, 或 user.lives_in."""
        return await self._kg.find_triples(
            user_id, subject=subject, predicate=predicate
        )

    async def search(
        self, user_id: str, query: str, top_k: int = 10
    ) -> list[tuple[MemoryRecord, float]]:
        """向量召回 (兜底)."""
        return await self._vector.search(
            user_id=user_id,
            query=query,
            memory_types=[MemoryType.SEMANTIC.value],
            top_k=top_k,
        )

    async def export_for_profile(self, user_id: str) -> dict[str, Any]:
        """导出用户所有 semantic 事实, 用于 Reflective Profile 生成."""
        triples = await self._kg.find_triples(user_id, subject="user")
        # 按 predicate 聚合
        facts: dict[str, list[str]] = {}
        for t in triples:
            facts.setdefault(t.predicate, []).append(t.object)
        return {"user_id": user_id, "facts": facts, "triple_count": len(triples)}


semantic_memory = SemanticMemory()
