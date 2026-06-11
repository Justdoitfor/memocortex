"""Pydantic 数据模型 — 全项目核心数据结构"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

# ╔══════════════════════════════════════════════════════════════════════╗
# ║                         记忆类型与记录                                ║
# ╚══════════════════════════════════════════════════════════════════════╝


class MemoryType(str, Enum):  # noqa: UP042  — 保持 Pydantic v2 兼容
    """5 类长期分层记忆 (对外 API 暴露).

    理论根基:
      - Tulving 1985 long-term memory 三分类 → EPISODIC / SEMANTIC / PROCEDURAL
      - 自研 REFLECTIVE: 显式用户画像 (Worker 周期从 Semantic 聚合)
      - 自研 IMPLICIT: 从行为信号挖掘的隐式偏好 (Pattern Miner 后台生成)
        参考 Honcho 的 dialectic pattern inference 思路

    WORKING (Baddeley 1974 short-term memory) 在内部保留作为 Episodic 缓冲层,
    **不对外 API 暴露** — 短期会话上下文是上游 Agent 框架 (LangGraph state /
    Redis) 的职责, 不是 *长期* 记忆中间件的职责.
    """

    EPISODIC = "episodic"         # 时序事件 ("X 时间发生了 Y")
    SEMANTIC = "semantic"         # 事实知识 (用户偏好/属性, 三元组)
    PROCEDURAL = "procedural"     # 程序性 (任务模板, 解决方法)
    REFLECTIVE = "reflective"     # 元记忆 / 显式用户画像 (Worker 聚合)
    IMPLICIT = "implicit"         # 隐式偏好 (Pattern Miner 从行为信号挖掘)

    # 内部使用, 不对外 API 暴露 — Episodic 路径的可选短期缓冲
    WORKING = "working"


class MemoryRecord(BaseModel):
    """单条记忆 — 统一数据模型, 5 类记忆都用此结构."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    user_id: str
    session_id: str | None = None
    type: MemoryType

    # 内容
    content: str = Field(min_length=1, description="可被向量化的自然语言文本")
    structured: dict[str, Any] = Field(
        default_factory=dict,
        description="结构化补充信息 (semantic 的 triple / procedural 的 steps 等)",
    )

    # 重要度 (0-1), 入库时 LLM/启发式打分, reflection 可更新
    importance: float = Field(default=0.5, ge=0.0, le=1.0)

    # 时序
    created_at: datetime = Field(default_factory=datetime.now)
    last_recalled_at: datetime | None = None
    recall_count: int = 0
    ttl_at: datetime | None = None  # 显式过期时间, 主要 working 用

    # 冷热分层
    tier: str = Field(default="hot", description="hot / cold / frozen")
    storage_uri: str | None = None  # cold/frozen 时指向 ColdStorage

    # 额外标签 (业务方自定义)
    tags: list[str] = Field(default_factory=list)

    # 来源 (供审计与冲突仲裁追溯)
    source: str = Field(default="explicit", description="explicit / distilled / merged / inferred")

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v

    def to_chroma_metadata(self) -> dict[str, Any]:
        """转 ChromaDB metadata — 只能存原始类型, 复杂结构 JSON 化."""
        import json

        return {
            "user_id": self.user_id,
            "session_id": self.session_id or "",
            "type": self.type.value,
            "importance": self.importance,
            "created_at_iso": self.created_at.isoformat(),
            "created_at_ts": self.created_at.timestamp(),
            "recall_count": self.recall_count,
            "tier": self.tier,
            "source": self.source,
            "structured_json": json.dumps(self.structured, ensure_ascii=False) if self.structured else "",
            "tags_csv": ",".join(self.tags),
        }


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                         知识图谱 Triple                              ║
# ╚══════════════════════════════════════════════════════════════════════╝


class Triple(BaseModel):
    """RDF 风格三元组 — Semantic Memory 的事实表示."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    subject: str          # 通常是 "user" 或具体实体
    predicate: str        # lives_in / likes / allergic_to / ...
    object: str           # 值
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_memory_id: str | None = None  # 该 triple 由哪条 MemoryRecord 派生
    created_at: datetime = Field(default_factory=datetime.now)
    valid_from: datetime | None = None  # for VERSIONED action
    valid_until: datetime | None = None


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                         冲突仲裁                                      ║
# ╚══════════════════════════════════════════════════════════════════════╝


class ConflictAction(str, Enum):  # noqa: UP042
    """冲突消解的 4 种动作."""

    REPLACE = "replace"       # 新事实覆盖旧的, 旧的归档
    MERGE = "merge"           # list 字段合并 (allergies / hobbies)
    VERSIONED = "versioned"   # 同时保留, 标记 valid_from/until
    IGNORE = "ignore"         # 新事实可疑, 不写 Semantic, 只记 Episodic


class ArbitrationDecision(BaseModel):
    """LLM-as-Arbitrator 的结构化输出."""

    action: ConflictAction
    reasoning: str = Field(description="为什么做这个决定, 一句话")
    confidence: float = Field(ge=0.0, le=1.0)
    merged_value: str | None = Field(
        default=None,
        description="action=MERGE 时, 合并后的新值 (e.g. '乳糖,花生')",
    )


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                         召回结果                                      ║
# ╚══════════════════════════════════════════════════════════════════════╝


class RecallSignals(BaseModel):
    """单条召回结果的 4 信号分数 — 用于可解释性."""

    vector_sim: float = 0.0
    temporal_decay: float = 0.0
    graph_proximity: float = 0.0
    importance: float = 0.0
    final_score: float = 0.0


class RecallResult(BaseModel):
    """Hybrid Recall 返回的单条结果."""

    record: MemoryRecord
    signals: RecallSignals
    rank: int = 0


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                         请求/响应 (API 层用)                          ║
# ╚══════════════════════════════════════════════════════════════════════╝


class WriteRequest(BaseModel):
    user_id: str
    content: str
    type: MemoryType = MemoryType.EPISODIC  # 默认 episodic, 由 Orchestrator 路由
    session_id: str | None = None
    importance: float | None = None
    tags: list[str] = Field(default_factory=list)
    structured: dict[str, Any] = Field(default_factory=dict)


class WriteResponse(BaseModel):
    memory_id: str
    routed_type: MemoryType
    arbitration: ArbitrationDecision | None = None  # 仅 semantic 写入时可能有


class SearchRequest(BaseModel):
    user_id: str
    query: str
    types: list[MemoryType] | None = None  # None = 全类型
    top_k: int = 8
    session_id: str | None = None
    score_threshold: float | None = None  # None=默认 0.55, 0.0=不过滤 (调试用)


class SearchResponse(BaseModel):
    results: list[RecallResult]
    latency_ms: float
    signals_used: list[str]


class ForgetRequest(BaseModel):
    user_id: str
    memory_id: str | None = None
    query: str | None = None  # 按语义模糊删除 (危险, 需 confirm)
    confirm: bool = False


class ProfileResponse(BaseModel):
    user_id: str
    profile: dict[str, Any]
    updated_at: datetime | None = None
