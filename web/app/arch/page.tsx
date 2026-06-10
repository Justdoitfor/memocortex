"use client";

import dynamic from "next/dynamic";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CodeBlock } from "@/components/shared/code-block";
import { Badge } from "@/components/ui/badge";
import { Info } from "lucide-react";

const MermaidDiagram = dynamic(
  () => import("@/components/shared/mermaid-diagram").then((m) => m.MermaidDiagram),
  { ssr: false, loading: () => <div className="h-96 animate-pulse rounded bg-zinc-100 dark:bg-zinc-900" /> }
);

const ARCH_CHART = `
flowchart TB
  subgraph Up["上游 Agent 框架"]
    LC[LangChain<br/>+ Adapter]
    AG[AutoGen<br/>+ Stub]
    CA[CrewAI<br/>+ Stub]
    MC[Claude Desktop<br/>via MCP]
  end

  subgraph Iface["统一接口"]
    REST[REST API]
    SDK[Python SDK]
    MCPS[MCP Server]
  end

  Up --> Iface

  subgraph Core["MemoCortex Core"]
    OR[Memory Orchestrator<br/>read/write/search/forget]
    OR --> W[Working]
    OR --> E[Episodic]
    OR --> S[Semantic]
    OR --> P[Procedural]
    OR --> R[Reflective]
    HR[Hybrid Recall Router<br/>4 信号融合]
    AR[Conflict Arbitrator<br/>LLM-as-Judge]
    RW[Reflection Workers<br/>4 周期任务]
    OR -.-> HR
    OR -.-> AR
    OR -.-> RW
  end

  Iface --> OR

  subgraph Store["存储层 (Protocol 抽象)"]
    Chroma[(ChromaDB<br/>向量)]
    NX[(NetworkX<br/>KG)]
    SQ[(SQLite + SQLAlchemy<br/>元数据)]
    FS[(本地文件<br/>冷存储)]
  end

  Core --> Store
`.trim();

const PYTHON_DIRECT = `import asyncio
from app.models import MemoryType, WriteRequest
from app.orchestrator import orchestrator

async def main():
    USER = "alice"
    # 1. 写入 (LLM 自动抽取 fact 到 KG)
    await orchestrator.write(WriteRequest(
        user_id=USER,
        content="我对花生过敏, 现在住在杭州",
        type=MemoryType.SEMANTIC,
    ))
    # 2. 等异步抽取完成
    await orchestrator.wait_pending()

    # 3. 召回 (4 信号 Hybrid Recall)
    resp = await orchestrator.search(user_id=USER, query="过敏原", top_k=3)
    for r in resp.results:
        print(f"[{r.rank}] score={r.signals.final_score:.2f} -> {r.record.content}")

    # 4. 用户画像 (Reflective Memory)
    profile = await orchestrator.get_profile(USER, auto_refresh=True)
    print(profile)

asyncio.run(main())
`;

const REST_CURL = `# 写入
curl -X POST http://localhost:8765/v1/memories \\
  -H "Content-Type: application/json" \\
  -d '{"user_id":"alice","content":"我对花生过敏","type":"semantic"}'

# 召回 (4 信号 Hybrid Recall)
curl -X POST http://localhost:8765/v1/memories/search \\
  -H "Content-Type: application/json" \\
  -d '{"user_id":"alice","query":"过敏原","top_k":5}'

# 用户画像 (Reflective Memory, auto_refresh=true 触发 LLM 即时生成)
curl "http://localhost:8765/v1/users/alice/profile?auto_refresh=true"

# 查 KG 三元组
curl "http://localhost:8765/v1/users/alice/entities/user"

# 仲裁审计日志
curl http://localhost:8765/admin/arbitrations/alice
`;

const PYTHON_SDK = `from app.sdks import MemoCortexClient

# 同步 Client (适合脚本和单进程应用)
with MemoCortexClient(base_url="http://localhost:8765") as mc:
    mc.write(user_id="alice", content="我搬家到上海了")
    mc.write(user_id="alice", content="我喜欢爬山和摄影")

    results = mc.search(user_id="alice", query="爱好", top_k=5)
    for r in results["results"]:
        print(r["record"]["content"])

    profile = mc.get_profile("alice", auto_refresh=True)
    mc.forget(user_id="alice", confirm=True)  # GDPR 级联删除

# 异步 Client (适合 FastAPI / 异步 Agent)
from app.sdks import AsyncMemoCortexClient
async with AsyncMemoCortexClient() as mc:
    await mc.write(user_id="bob", content="我换工作了")
`;

const LANGCHAIN_ADAPTER = `from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from app.adapters import MemoCortexChatHistory

# MemoCortex 替换 LangChain 自带的 InMemoryChatMessageHistory
def get_history(session_id: str):
    return MemoCortexChatHistory(
        user_id="alice",
        session_id=session_id,
        inject_profile=True,   # 自动在 SystemMessage 注入用户画像
    )

llm = ChatOpenAI(model="deepseek-chat", base_url="https://api.deepseek.com/v1")
prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个贴心的 AI 助手"),
    MessagesPlaceholder("history"),
    ("human", "{input}"),
])
chain = prompt | llm
chain_with_memory = RunnableWithMessageHistory(
    chain, get_history,
    input_messages_key="input", history_messages_key="history",
)

# 跨 session 的长期记忆自动生效
config = {"configurable": {"session_id": "s1"}}
chain_with_memory.invoke({"input": "我对花生过敏"}, config=config)

# 切到 s2, bot 仍然记得 alice 的过敏原 (通过 Reflective Profile)
chain_with_memory.invoke({"input": "推荐一家餐厅"},
                         config={"configurable": {"session_id": "s2"}})
`;

const MCP_CONFIG = `// Claude Desktop 配置文件位置:
// macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json
// Windows: %APPDATA%\\Claude\\claude_desktop_config.json

{
  "mcpServers": {
    "memocortex": {
      "url": "http://localhost:8766/mcp",
      "transport": "streamable-http"
    }
  }
}

// 启动 MCP Server (在 memocortex 仓库根目录):
//   make mcp
//
// 重启 Claude Desktop, 它现在能自主调用以下 5 个工具:
//   - memory_search          召回历史相关记忆
//   - memory_write           记录用户事实
//   - memory_get_profile     查用户画像
//   - memory_forget          删除记忆 (GDPR)
//   - memory_list_arbitrations 查看冲突仲裁审计
`;

const LANGCHAIN_TOOL = `from langchain_core.tools import tool
from app.orchestrator import orchestrator
from app.models import WriteRequest, MemoryType

# 把 MemoCortex 包装成 LangChain Tool, 让 Agent 主动决定何时调用
USER_ID = "alice"  # 通常从请求 context 取

@tool
async def remember(content: str) -> str:
    """记住关于用户的事实(偏好/属性/重要事件)。
    当用户透露任何持久信息时立即调用。"""
    res = await orchestrator.write(WriteRequest(
        user_id=USER_ID, content=content, type=MemoryType.SEMANTIC
    ))
    return f"已记住, memory_id={res.memory_id[:8]}"

@tool
async def recall(query: str) -> str:
    """查询用户的历史记忆。回答个性化问题前必须先调用。"""
    resp = await orchestrator.search(user_id=USER_ID, query=query, top_k=5)
    if not resp.results:
        return "没有相关记忆"
    return "\\n".join(f"- {r.record.content}" for r in resp.results[:5])

# 注册到 Agent
from langgraph.prebuilt import create_react_agent
agent = create_react_agent(llm, tools=[remember, recall])
`;

const ACCESS_METHODS = [
  { key: "python", label: "Python 直接调用", badge: "最简单",
    desc: "无需启服务, import 后直接用 orchestrator. 适合个人脚本和原型.",
    code: PYTHON_DIRECT, lang: "python", filename: "demo_basic.py" },
  { key: "rest", label: "REST API", badge: "通用",
    desc: "启 make api 后任何语言/任何系统都能 HTTP 调用. 浏览器开 /docs 看 Swagger.",
    code: REST_CURL, lang: "bash", filename: "curl_examples.sh" },
  { key: "sdk", label: "Python SDK", badge: "推荐",
    desc: "MemoCortexClient 提供同步+异步双 Client, 自带重试. 适合 Python 项目接入.",
    code: PYTHON_SDK, lang: "python", filename: "use_sdk.py" },
  { key: "langchain", label: "LangChain Adapter", badge: "高频",
    desc: "继承 BaseChatMessageHistory, 一行代码替换 LangChain 自带 Memory.",
    code: LANGCHAIN_ADAPTER, lang: "python", filename: "langchain_chatbot.py" },
  { key: "mcp", label: "MCP Server", badge: "新潮",
    desc: "Claude Desktop / Cursor / Cline 等 MCP 客户端零侵入接入, LLM 自主调用 5 个工具.",
    code: MCP_CONFIG, lang: "json", filename: "claude_desktop_config.json" },
  { key: "tool", label: "LangChain Tool", badge: "Agent 友好",
    desc: "把 MemoCortex 包装成 @tool, 让 Agent 自己决定何时记忆/召回.",
    code: LANGCHAIN_TOOL, lang: "python", filename: "memory_tools.py" },
];

export default function ArchPage() {
  return (
    <div className="space-y-10">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">架构 & 接入方式</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          MemoCortex 整体架构图 + 6 种姿势把它接入你的项目, 一键复制即用.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>整体架构</CardTitle>
          <CardDescription>
            从上游 Agent 框架 → 统一接口 → Core → 存储层的完整分层
          </CardDescription>
        </CardHeader>
        <CardContent>
          <MermaidDiagram chart={ARCH_CHART} id="arch-main" />
        </CardContent>
      </Card>

      <div className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-2xl font-semibold tracking-tight">6 种接入方式</h2>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            <Info className="mr-1 inline h-3 w-3" />
            选符合你技术栈的姿势, 5 行代码起步
          </span>
        </div>

        <Tabs defaultValue="python" className="w-full">
          <TabsList className="flex flex-wrap h-auto">
            {ACCESS_METHODS.map((m) => (
              <TabsTrigger key={m.key} value={m.key}>
                {m.label}
              </TabsTrigger>
            ))}
          </TabsList>

          {ACCESS_METHODS.map((m) => (
            <TabsContent key={m.key} value={m.key} className="space-y-4">
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-2">
                    <CardTitle className="text-lg">{m.label}</CardTitle>
                    <Badge variant="secondary">{m.badge}</Badge>
                  </div>
                  <CardDescription>{m.desc}</CardDescription>
                </CardHeader>
                <CardContent>
                  <CodeBlock code={m.code} lang={m.lang} filename={m.filename} />
                </CardContent>
              </Card>
            </TabsContent>
          ))}
        </Tabs>
      </div>
    </div>
  );
}
