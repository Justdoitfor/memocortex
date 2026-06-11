"use client";

import Link from "next/link";
import { ArrowRight, Brain, Network, Zap, ShieldCheck, Layers, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const MEMORY_TYPES = [
  {
    name: "Episodic",
    cn: "情景记忆",
    icon: Zap,
    desc: "时序事件, ChromaDB + SQLite 双写, 异步触发 Semantic 抽取",
    color: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
  },
  {
    name: "Semantic",
    cn: "语义记忆",
    icon: Network,
    desc: "事实知识三元组, NetworkX KG + ChromaDB 双索引",
    color: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  },
  {
    name: "Procedural",
    cn: "程序记忆",
    icon: Layers,
    desc: "任务模板与解决方法, 按使用频率衰减",
    color: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  },
  {
    name: "Reflective",
    cn: "反思记忆",
    icon: Brain,
    desc: "显式用户画像, Reflection Worker 从 Semantic 聚合, 注入 SystemMessage",
    color: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
  },
  {
    name: "Implicit",
    cn: "隐式偏好",
    icon: Sparkles,
    desc: "Pattern Miner 从行为信号 (regenerate/correction/format_pref) 自动挖掘",
    color: "bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-900/30 dark:text-fuchsia-300",
  },
] as const;

const HIGHLIGHTS = [
  { num: "27/30", label: "LongMemEval-style CN", color: "text-emerald-600" },
  { num: "8/8", label: "cn_scenarios 冲突仲裁", color: "text-violet-600" },
  { num: "< 20ms", label: "Hybrid Recall P95", color: "text-sky-600" },
];

const COMPARISON = [
  {
    key: "记忆分层",
    mem0: "2 类 + entity",
    zep: "时序为主",
    letta: "单 Agent OS",
    ours: "5 类长期 (Episodic/Semantic/Procedural/Reflective/Implicit)",
  },
  {
    key: "召回信号",
    mem0: "3 信号 (语义+BM25+entity)",
    zep: "向量+时序",
    letta: "上下文窗口管理",
    ours: "4 信号 (+ 时间衰减/重要度)",
  },
  {
    key: "冲突消解",
    mem0: "ADD-only + 召回 rerank",
    zep: "部分",
    letta: "不强",
    ours: "LLM Arbitrator + 4 action + 审计",
  },
  {
    key: "MCP Server",
    mem0: "❌",
    zep: "❌",
    letta: "❌",
    ours: "✅ 5 个工具",
  },
  {
    key: "Reflective Profile",
    mem0: "❌",
    zep: "❌",
    letta: "❌",
    ours: "✅ Worker 周期刷新",
  },
  {
    key: "定位",
    mem0: "Agent 内部模块",
    zep: "时序记忆库",
    letta: "Agent OS",
    ours: "MCP-Native 长期记忆基础设施",
  },
];

export default function Home() {
  return (
    <div className="space-y-12">
      {/* Hero */}
      <section className="space-y-6 pt-4">
        <div className="space-y-3">
          <Badge variant="secondary">MVP · 2026-06 · Powered by DeepSeek-v4-pro</Badge>
          <h1 className="text-4xl font-bold tracking-tight md:text-5xl">
            <span className="text-emerald-600">MemoCortex</span> —
            <br />
            MCP-Native 长期记忆基础设施
          </h1>
          <p className="max-w-3xl text-base text-zinc-600 dark:text-zinc-400 md:text-lg">
            为 Claude Desktop / Cursor / Cline 等 MCP 客户端原生设计的 Agent 长期
            记忆服务 — <b>5 类长期记忆</b>(Episodic / Semantic / Procedural /
            Reflective / Implicit)+ 4 信号 Hybrid Recall + LLM-as-Arbitrator
            冲突消解 + Staleness Detection 软废弃 + Pattern Miner 隐式偏好挖掘。
            MCP 工具一等公民, 同时提供 REST / Python SDK 接入 LangChain 等其他框架。
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/playground">
              去 Playground 试玩 <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="/conflict">看 LLM 冲突仲裁动画</Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="/arch">架构 & MCP 接入</Link>
          </Button>
        </div>

        {/* Highlights */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {HIGHLIGHTS.map((h) => (
            <Card key={h.label}>
              <CardContent className="p-6">
                <div className={`text-3xl font-bold ${h.color}`}>{h.num}</div>
                <div className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{h.label}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* 5 类长期记忆 */}
      <section>
        <h2 className="mb-4 text-2xl font-semibold tracking-tight">5 类长期分层记忆架构</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-5">
          {MEMORY_TYPES.map((m) => {
            const Icon = m.icon;
            return (
              <Card key={m.name} className="hover:shadow-md transition-shadow">
                <CardHeader className="pb-3">
                  <div
                    className={`mb-2 inline-flex h-10 w-10 items-center justify-center rounded-lg ${m.color}`}
                  >
                    <Icon className="h-5 w-5" />
                  </div>
                  <CardTitle className="text-base">{m.name}</CardTitle>
                  <div className="text-xs text-zinc-500 dark:text-zinc-400">{m.cn}</div>
                </CardHeader>
                <CardContent className="pt-0">
                  <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
                    {m.desc}
                  </p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      {/* vs 对比 */}
      <section>
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-2xl font-semibold tracking-tight">
            与 mem0 / Zep / Letta 对比
          </h2>
          <span className="text-xs text-zinc-500">已对齐 mem0 v2.0.4 (2026-05)</span>
        </div>
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
                  <th className="px-4 py-3 text-left font-medium">维度</th>
                  <th className="px-4 py-3 text-left font-medium">mem0 v2.0.4</th>
                  <th className="px-4 py-3 text-left font-medium">Zep</th>
                  <th className="px-4 py-3 text-left font-medium">Letta</th>
                  <th className="px-4 py-3 text-left font-medium text-emerald-700 dark:text-emerald-400">
                    MemoCortex
                  </th>
                </tr>
              </thead>
              <tbody>
                {COMPARISON.map((row) => (
                  <tr
                    key={row.key}
                    className="border-b border-zinc-100 dark:border-zinc-800/50 last:border-0"
                  >
                    <td className="px-4 py-3 font-medium">{row.key}</td>
                    <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">{row.mem0}</td>
                    <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">{row.zep}</td>
                    <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">{row.letta}</td>
                    <td className="px-4 py-3 font-medium text-emerald-700 dark:text-emerald-400">
                      {row.ours}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
          <ShieldCheck className="mr-1 inline h-3 w-3" />
          mem0 v2 选择"写入侧极简 + 召回侧重 rank"; MemoCortex 选择"写入侧主动消解 +
          完整审计可回滚"。两条路线在不同业务场景各有取舍。
        </p>
      </section>
    </div>
  );
}
