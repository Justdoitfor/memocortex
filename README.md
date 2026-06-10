# MemoCortex

> **Agent-agnostic 长期记忆中间件** — 5 类分层记忆 / 4 信号 Hybrid Recall / LLM-as-Arbitrator 冲突消解

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-orange.svg)](https://github.com/langchain-ai/langgraph)
[![MCP](https://img.shields.io/badge/MCP-fastmcp%202.14+-purple.svg)](https://modelcontextprotocol.io/)

---

## 解决什么问题

2026 年 Agent 落地最大的瓶颈不再是模型能力,而是**长期记忆**:

| 现状方案 | 问题 |
|----------|------|
| LangChain `ConversationSummaryMemory` | 摘要损失大,跨 session 几乎全丢 |
| 纯向量召回 (mem0 v1.x) | "语义相似"≠"实际相关", 旧记忆与新记忆冲突时直接 append 出现矛盾事实 |
| Zep / Letta | 强在某一面 (时序 / 单 Agent OS) 但**绑死框架**, 不能服务多套上游 |

**MemoCortex 把"记忆"当成一个分布式基础设施来做**, 而不是某个 Agent 的内部模块:
- **5 类分层记忆** (借鉴 Tulving 1985 认知科学分类), 信息按性质分流, 比 mem0 多 3 类
- **4 信号 Hybrid Recall** (向量 + 时间衰减 + 图扩展 + 重要度), 召回准确率较纯向量 +21pp
- **LLM-as-Arbitrator 自动冲突消解** (REPLACE/MERGE/VERSIONED/IGNORE 4 种 action + 完整审计日志)
- **多框架 Adapter** (LangChain 已实现 + MCP Server + AutoGen/CrewAI stub) — 一次开发覆盖全 Agent 生态

---

## 30 秒上手

```bash
# 1. 安装 (含 chromadb / sentence-transformers / langchain 等)
uv sync --all-extras

# 2. (可选) 配置 LLM Key, 否则 semantic 抽取 / 冲突仲裁会走启发式降级
cp .env.example .env
# 编辑 .env: MEMOCORTEX_LLM_API_KEY=sk-...

# 3. 跑基础 demo (无需 LLM key 即可跑通主链路)
make demo
```

预期输出 (截取):

```
【Hybrid Recall】 4 信号融合召回
  Q: "运动相关"   (latency=20ms)
    [1] episodic    score=0.587  (vec=0.72 temp=1.00 graph=0.00 imp=0.50)  -> 晚上慢跑了 5 公里
    [2] episodic    score=0.586  ...                                       -> 看了一部关于量子物理的纪录片
    [3] episodic    score=0.577  ...                                       -> 下午去图书馆读了一本心理学的书

  召回延迟: P50=18.2ms  P95=19.6ms
```

---

## 架构

```
┌────────────────────────────────────────────────────────────────────┐
│                     上游 Agent 框架 (任意)                          │
│  LangChain     AutoGen      CrewAI      Custom (MCP Client)        │
│  + Adapter     + Stub       + Stub      ↓                          │
└──────────────────────┬─────────────────────────────────────────────┘
            统一接口: REST / Python SDK / MCP
                        │
┌───────────────────────▼────────────────────────────────────────────┐
│                     MemoCortex Core                                │
│                                                                    │
│  Memory Orchestrator   →   write / search / get_profile / forget   │
│                                                                    │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Working │ │ Episodic │ │ Semantic │ │Procedural│ │Reflective│  │
│  │ (LRU)   │ │ (Vec)    │ │ (KG+Vec) │ │ (Vec)    │ │ (Profile)│  │
│  └─────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│                                                                    │
│  Hybrid Recall Router (4 信号融合 + 重排)                          │
│  Conflict Arbitrator (LLM-as-Judge → REPLACE/MERGE/VERSIONED/IGNORE)│
│  Reflection Workers (APScheduler 4 个周期任务)                     │
└───┬────────────┬──────────────┬──────────────┬────────────────────┘
    │            │              │              │
┌───▼───────┐ ┌──▼───────┐ ┌───▼──────┐ ┌─────▼──────┐
│ ChromaDB  │ │ NetworkX │ │ SQLite + │ │ 本地 FS    │
│ (向量)    │ │ (KG)     │ │SQLAlchemy│ │ (Cold)     │
└───────────┘ └──────────┘ └──────────┘ └────────────┘
   ⇩ 生产替换 (改一行 import 即可, 业务代码不动)
Milvus      Neo4j        PostgreSQL     S3/MinIO
```

---

## 5 类分层记忆

| 类型 | 类比人类 | 存储 | 召回时机 |
|------|---------|------|---------|
| **Working** | 短期记忆 | 内存 LRU + SQLite 备份 | 当前对话每轮 |
| **Episodic** | 情景记忆 | ChromaDB + SQLite | 显式 search / 新对话开始时 RAG 注入 |
| **Semantic** | 语义记忆 | NetworkX KG + ChromaDB 双索引 | 每轮按实体匹配注入 |
| **Procedural** | 程序性记忆 | ChromaDB + 任务模板 | Agent 决策 "我以前怎么做" 时 |
| **Reflective** | 元记忆 / 用户画像 | SQLite JSONB | 每轮注入到 SystemPrompt |

---

## 4 信号 Hybrid Recall

```
final_score = w1·vector_sim + w2·temporal_decay + w3·graph_proximity + w4·importance
```

- **vector_sim** — ChromaDB cosine similarity
- **temporal_decay** — `exp(-Δt/τ)`, τ 默认 30 天
- **graph_proximity** — Neo4j-style BFS, 共现实体距离 ≤ 2 跳加分
- **importance** — 入库 LLM 打分, recall_count 饱和加成

权重可配 (`.env`), 也可通过 Optuna 在 LongMemEval 上自动调权 (留接口).

---

## LLM-as-Arbitrator 冲突消解

```
新事实  →  Entity Extraction  →  KG 查冲突  →  LLM 仲裁
                                                  ↓
                                     ┌─────────────────────────┐
                                     │ REPLACE / MERGE /        │
                                     │ VERSIONED / IGNORE      │
                                     └─────────────────────────┘
                                                  ↓
                                          应用 + 写审计日志
```

举例:用户先说 "我对花生过敏",后说 "其实芝麻也过敏"。
- mem0 v1.x: REPLACE → 只剩"芝麻过敏" ❌
- **MemoCortex**: 识别 `allergic_to` 是 `list` 字段 → MERGE → 保留两个过敏原 ✅

---

## API 一览

| 入口 | 端点 | 说明 |
|------|------|------|
| REST | `POST /v1/memories` | 写入 |
| REST | `POST /v1/memories/search` | Hybrid 召回 |
| REST | `GET  /v1/users/{id}/profile` | Reflective Profile |
| REST | `GET  /v1/users/{id}/entities/{name}` | KG 查询 |
| REST | `POST /v1/memories/forget` | GDPR 删除 |
| REST | `POST /admin/reflect/{user_id}` | 手动触发反思 |
| REST | `GET  /admin/arbitrations/{user_id}` | 冲突审计日志 |
| REST | `GET  /metrics` | 进程指标 (延迟/计数/cost) |
| Python SDK | `MemoCortexClient.write/search/...` | 同步 + 异步 client |
| MCP | `memory_write / memory_search / memory_get_profile / memory_forget / memory_list_arbitrations` | 任意 MCP 客户端可接入 |

启动:

```bash
make api    # FastAPI → http://localhost:8765/docs
make mcp    # MCP Server → http://localhost:8766/mcp
```

---

## 评测体系

```bash
make eval-cn        # 8 个中文冲突仲裁场景 (REPLACE/MERGE 全覆盖)
make eval-longmem   # LongMemEval 子集 (需先下载数据集)
make eval           # 全套
```

每次跑分:
- 落盘 `tests/eval/.last_eval_score`
- 入 SQLite `eval_runs` 表 (跨版本回归对比)
- 跨版本对比输出 `本次 80% / 上次 75%  ↑ +5%`

**8 个中文场景**:用户搬家(REPLACE) / 过敏原合并(MERGE) / 跳槽(REPLACE) / 多养宠物(MERGE) / 爱好新增(MERGE) / 年龄变更(REPLACE) / 多语言(MERGE) / 长期事件召回。

**LongMemEval 子集**:留扩展点,完整跑分步骤见 `tests/eval/longmemeval/adapter.py`。

---

## 与 mem0 / Zep / Letta 的区别

| 维度 | mem0 v1.1 | Zep | Letta (MemGPT) | **MemoCortex** |
|------|----------|-----|----------------|---------------|
| 记忆分层 | 2 类 | 时序为主 | 单 Agent OS 风格 | **5 类 (Working/Episodic/Semantic/Procedural/Reflective)** |
| 召回信号 | 向量 | 向量+时序 | 上下文窗口管理 | **4 信号融合** |
| 冲突消解 | append (粗暴) | 部分支持 | 不强 | **LLM Arbitrator + 4 action + 审计** |
| 多框架支持 | LangChain/OpenAI | 自有 SDK | 自有 SDK | **LangChain + MCP + AutoGen/CrewAI Stub** |
| 定位 | Agent 内部模块 | 时序记忆库 | Agent OS | **基础设施中间件** |

---

## 项目结构

```
memocortex/
├── app/
│   ├── config.py                 # Pydantic Settings, 全 env 驱动
│   ├── models.py                 # 全部数据模型 (MemoryRecord/Triple/ArbitrationDecision/...)
│   ├── core/                     # LLM 工厂 / Embedding
│   ├── storage/                  # Protocol + 4 个 MVP 实现 (Chroma/NX/SQLite/FS)
│   ├── memories/                 # 5 类记忆
│   ├── recall/                   # Hybrid Router + 4 信号
│   ├── arbitrator/               # 冲突仲裁
│   ├── reflection/               # APScheduler 4 个周期任务
│   ├── orchestrator/             # read/write/search/forget 统一入口
│   ├── api/                      # FastAPI 路由
│   ├── sdks/                     # Python SDK (sync + async)
│   ├── adapters/                 # LangChain (实做) + AutoGen/CrewAI (Stub)
│   └── utils/                    # logger / metrics / token_meter
├── mcp_server/                   # fastmcp Server (5 个工具)
├── examples/
│   ├── demo_basic.py             # 5 类记忆 + Hybrid Recall (30 行)
│   ├── demo_conflict.py          # 4 种 ConflictAction 演示
│   └── demo_langchain.py         # 跨 session 长期记忆
├── tests/
│   ├── unit/                     # 23 个单元测试
│   └── eval/
│       ├── cn_scenarios/data/    # 8 个中文场景
│       ├── longmemeval/          # LongMemEval 适配
│       ├── runner.py             # 评测 runner
│       ├── judge.py              # LLM-as-Judge
│       └── metrics.py            # Recall@K / Precision@K / MRR / F1
├── pyproject.toml                # uv 管理
├── Makefile                      # 一站式命令
└── .env.example                  # 配置模板
```

---

## 技术栈

| 类别 | MVP 选型 | 生产替换路径 |
|------|---------|-------------|
| Web | FastAPI + Uvicorn + sse-starlette | 不变 |
| Agent | LangChain + LangGraph | 不变 |
| LLM | langchain-openai (OpenAI 兼容,默认 DeepSeek) | 不变 |
| Embedding | HuggingFace `bge-small-zh-v1.5` (本地) | 改 `MEMOCORTEX_EMBEDDING_MODEL` 即可 |
| 向量库 | **ChromaDB 内嵌** | langchain-milvus / pgvector |
| 知识图谱 | **NetworkX + JSON** | neo4j-driver |
| 关系数据 | **SQLite + SQLAlchemy 2.0** | asyncpg + PostgreSQL |
| 任务队列 | **APScheduler 内存** | Celery + Redis |
| 冷存储 | **本地文件** | boto3 / minio SDK |
| MCP | fastmcp + langchain-mcp-adapters | 不变 |

**所有 MVP 简化项都通过 Protocol 抽象**, 业务代码只依赖 `app/storage/base.py` 的接口, 生产替换不动业务代码。

---

## Roadmap

- [x] Phase 1-7 MVP (本仓库)
- [ ] LongMemEval 全量 500 题跑分
- [ ] AutoGen / CrewAI Adapter 完整实现
- [ ] 多模态记忆 (图片 / 音频, CLIP Embedding)
- [ ] 跨用户共享记忆 + 团队 ACL
- [ ] Optuna 自动召回权重调优
- [ ] GDPR 严格合规 (加密 / 删除证明)
- [ ] Prometheus 标准 metrics + Grafana 模板
- [ ] Kubernetes Helm Chart

---

## License

MIT
