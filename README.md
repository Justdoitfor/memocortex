# MemoCortex

> **MCP-Native Long-Term Memory Infrastructure** — 5 类长期分层记忆 / 4 信号 Hybrid Recall / LLM-as-Arbitrator + Staleness Detection 双策略 / 隐式行为模式挖掘

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-orange.svg)](https://github.com/langchain-ai/langgraph)
[![MCP](https://img.shields.io/badge/MCP-fastmcp%202.14+-purple.svg)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🌐 **Live Demo**: 部署后填 `https://memocortex.vercel.app`
> 📦 **GitHub**: https://github.com/Justdoitfor/memocortex
> 📖 **Claude Desktop 一键接入**: 见 [§ MCP 集成](#-mcp-集成-claude-desktop--cursor--cline)

---

## 解决什么问题

2026 年 Agent 落地最大的瓶颈不再是模型能力, 而是 **长期记忆系统**. mem0 官方 *State of AI Agent Memory 2026* 报告点名 5 个 open problem:

| Open Problem | 行业现状 | MemoCortex 方案 |
|--------------|---------|----------------|
| **记忆陈旧性** (高置信度记忆事实过期后仍被高频召回) | mem0 v3 选 ADD-only, 旧事实留库靠 rank 压 | **Staleness Detection** — Ebbinghaus 公式 + 软废弃罚分 × 0.2 + 完整审计可回滚 |
| **隐式偏好学习** (用户从未明说但行为体现) | 仅 Honcho 在做, 方案黑盒 | **Pattern Miner** — 6 类行为信号 + 周期 LLM 归纳为 Implicit Memory |
| **跨会话身份归因** | 各方案普遍混淆 inferred / explicit | **source_type** 6 类 + 影响 effective_strength 计算 |
| **程序性记忆工具链** | 概念支持, 工具空白 | **Procedural Memory** + 专用 MCP `recall_workflow` 工具 |
| **MCP 生态原生集成** | 都是事后 wrapper | **8 个动词驱动 MCP Tools + 3 个 Resources** (一等公民) |

**MemoCortex 是 MCP 一等公民的长期记忆基础设施**, REST/SDK 为附加协议. 上游 Agent 框架 (LangChain/AutoGen/CrewAI) 通过 MCP 零侵入接入.

---

## 5 类长期分层记忆 (5 + 1)

| 类型 | 定位 | 来源 | 何时被召回 |
|------|------|------|-----------|
| **Episodic** | 时序事件 | 业务方写入 (默认) | 显式 search 或新对话开头 |
| **Semantic** | 事实知识 (KG triple) | LLM 抽取 + 冲突仲裁 | 每轮按实体匹配注入 |
| **Procedural** | 任务模板 + 步骤 | 业务方写入 (含 structured.steps) | Agent 决策"我以前怎么做"时 |
| **Reflective** | 显式用户画像 | Worker 从 Semantic 周期聚合 (不可手动写) | 每轮注入 SystemPrompt |
| **Implicit** | 隐式偏好 | **Pattern Miner 从行为信号挖掘** (不可手动写) | 高置信场景注入 |
| ~~Working~~ | 短期会话上下文 | **内部缓冲, 不对外暴露** (那是 LangGraph state 的职责) | — |

> 理论根基: Tulving 1985 long-term memory 三分类 (Episodic/Semantic/Procedural) + 自研 Reflective (Worker 聚合) + 自研 Implicit (Honcho 风格 pattern mining).

---

## 4 信号 Hybrid Recall

```
final_score = w1·vector_sim       # 向量召回 (语义相似)
            + w2·temporal_decay   # 时间衰减 (exp(-Δt/τ), τ=30 天)
            + w3·bm25_score       # SQLite FTS5 BM25 (字面 / 罕见词命中)
            + w4·importance       # effective_strength (含 staleness × 0.2 软废弃)

权重默认 0.40 / 0.20 / 0.20 / 0.20, 可热配置.
```

**effective_strength 公式** (Phase 1, MemoryMesh §5.1):
```
effective_strength(t) = confidence_score
                       × e^(-decay_rate × active_days)        # Ebbinghaus
                       × (1 + 0.15 × log(recall_count + 1))   # 复习提升
                       × SOURCE_WEIGHTS[source_type]           # 来源权重
                       × (0.2 if staleness_signal else 1.0)    # 软废弃罚分
```

实测分数:
- 新写入的 explicit_statement: **1.000**
- 30 天未召回: **0.741** (e^(-0.3))
- 高频召回 50 次: **1.590** (复习提升)
- 软废弃: **0.200**
- 用户主动纠正 (corrected): **1.200**

---

## 🌐 MCP 集成 (Claude Desktop / Cursor / Cline)

**Claude Desktop 配置** (`~/Library/Application Support/Claude/claude_desktop_config.json` macOS, `%APPDATA%\Claude\claude_desktop_config.json` Windows):

```json
{
  "mcpServers": {
    "memocortex": {
      "url": "http://127.0.0.1:8766/mcp",
      "transport": "streamable-http"
    }
  }
}
```

**8 个动词驱动 MCP Tools** (`uv run python -m mcp_server.server` 启动):

| Tool | 描述 |
|------|------|
| `remember` | 写入长期记忆 (episodic/semantic/procedural) |
| `recall` | 4 信号 Hybrid Recall (含 vector_sim ≥ 0.55 阈值过滤) |
| `recall_workflow` | 检索 Procedural Memory, 返回结构化步骤 |
| `get_profile` | 获取 Reflective Memory 用户画像 |
| `track_signal` | 上报 6 类行为信号 (Phase 2 Pattern Miner) |
| `reflect` | 手动触发 Pattern Miner 挖掘 Implicit |
| `manage_memory` | list / forget / mark_stale 统一管理 |
| `list_arbitrations` | 查询冲突仲裁审计日志 |

**3 个 MCP Resources** (Agent SystemPrompt 注入):
- `memory://summary/{user_id}` — 核心 Semantic 摘要
- `memory://profile/{user_id}` — 用户画像 Markdown
- `memory://workflows/{user_id}` — 所有 Procedural 索引


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
- mem0 v2 (2026-04+): ADD-only + 哈希去重,两条事实并存,靠召回 rank 处理 — 体验上"花生"还会被召回,得让上层 Agent 自己挑
- **MemoCortex**: 识别 `allergic_to` 是 `list` 字段 → LLM 主动 MERGE → KG 中只保留一条合并后的多值事实,带审计日志可回滚 ✅

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

## 与 mem0 / Zep / Letta 的区别 (已对齐 mem0 v2.0.4, 2026-05 最新版)

| 维度 | **mem0 v2.0.4** (2026-05) | Zep | Letta (MemGPT) | **MemoCortex** |
|------|--------------------------|-----|----------------|---------------|
| 记忆分层 | 2 类 (user / agent memory) + entity collection | 时序为主 | 单 Agent OS 风格 | **5 类 (Working/Episodic/Semantic/Procedural/Reflective)** |
| 召回信号 | **3 信号融合** (语义 + BM25 + entity boost,v2 新增) | 向量 + 时序 | 上下文窗口管理 | **4 信号** (向量 + **时间衰减** + 图扩展 + **重要度**) |
| 冲突消解 | **ADD-only + 哈希去重 + 召回 rank** (v2 新路线) | 部分支持 | 不强 | **LLM Arbitrator + 4 action + 完整审计可回滚** |
| 知识图谱 | **内置 entity linking** (v2 移除 Neo4j) | 无 | 无 | NetworkX KG (MVP) / Neo4j (生产) + entity 双索引 |
| MCP Server | ❌ | ❌ | ❌ | ✅ **5 个工具** |
| Reflective Profile | ❌ | ❌ | ❌ | ✅ 后台 Worker 周期刷新 |
| 多框架支持 | Python SDK + Platform API | 自有 SDK | 自有 SDK | **REST + SDK + MCP + LangChain Adapter** |
| 定位 | Agent 内部模块 | 时序记忆库 | Agent OS | **Agent-agnostic 基础设施中间件** |

> mem0 v2 (2026-04 发布) 做了架构级重写, 在 Hybrid Retrieval 和 entity linking 上追上了一代差距,但路线选择完全不同:
> - **mem0 v2 选择**: 写入侧极简 (ADD-only), 召回侧重 rank, 强调低延迟
> - **MemoCortex 选择**: 写入侧主动消解 (LLM Arbitrator + 审计), 召回侧 4 信号融合, 强调可解释与可回滚
>
> 两条路线在不同业务场景各有取舍。MemoCortex 更适合需要"用户画像稳定、事实变更可追溯"的企业场景。

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

## 部署 (Phase 4)

### 本地一键跑

```bash
# 后端
make api          # → http://localhost:8765 (REST + Swagger)
make mcp          # → http://localhost:8766/mcp (MCP Server)

# 前端
cd web && npm install && npm run build && cd out && python -m http.server 3000
# → http://localhost:3000
```

### Vercel + Render 一键上线 (公网 Demo)

**前端 (Vercel)** — `web/` 子目录已配置 `vercel.json`:
```bash
# 1. 把仓库连到 Vercel (https://vercel.com/new)
# 2. Root Directory 选 `web/`, 自动识别 Next.js + vercel.json
# 3. 在 Vercel 项目 Settings → Environment Variables 加:
#    NEXT_PUBLIC_API_BASE=https://memocortex-api.onrender.com
# 4. Deploy → 拿到 https://memocortex.vercel.app
```

**后端 (Render)** — 根目录已配置 `Dockerfile` + `render.yaml`:
```bash
# 1. https://dashboard.render.com → New + → Blueprint → 选 memocortex 仓库
# 2. Render 自动识别 render.yaml, 创建 web service
# 3. 在 Render dashboard 设置 Environment:
#    MEMOCORTEX_LLM_API_KEY = sk-xxx  (DeepSeek/OpenAI 兼容 key)
# 4. Deploy → 拿到 https://memocortex-api.onrender.com
# 5. 把这个 URL 回填到 Vercel 前端的 NEXT_PUBLIC_API_BASE
```

### Docker 自托管

```bash
docker build -t memocortex:latest .
docker run -p 8765:8765 \
  -e MEMOCORTEX_LLM_API_KEY=sk-xxx \
  -v $(pwd)/data:/data \
  memocortex:latest
```

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
