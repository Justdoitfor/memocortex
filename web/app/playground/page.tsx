"use client";

import { useState, useMemo } from "react";
import dynamic from "next/dynamic";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Send, Search, Trash2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScoreBar } from "@/components/shared/score-bar";
import { writeMemory, searchMemories, getStats, forgetUser } from "@/lib/api";
import type { MemoryType, SearchResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const KgGraph = dynamic(
  () => import("@/components/shared/kg-graph").then((m) => m.KgGraph),
  { ssr: false, loading: () => <div className="h-[420px] animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-900" /> }
);

// ── 快捷模板 ─────────────────────────────────────────────────────────
const TEMPLATES = [
  { content: "我对花生过敏, 同时不能吃乳糖", type: "semantic" as MemoryType },
  { content: "我现在住在杭州滨江区, 在一家 AI 创业公司工作", type: "semantic" as MemoryType },
  { content: "我喜欢爬山和摄影", type: "semantic" as MemoryType },
  { content: "昨晚去吃了川菜火锅, 喝了两瓶啤酒", type: "episodic" as MemoryType },
  { content: "我搬家了, 现在住在上海浦东", type: "semantic" as MemoryType },
  { content: "周末跟朋友去了西湖", type: "episodic" as MemoryType },
];

const TYPE_COLORS: Record<MemoryType, string> = {
  working: "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300",
  episodic: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
  semantic: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  procedural: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  reflective: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
};

const TYPE_LABELS: Record<MemoryType, string> = {
  working: "Working", episodic: "Episodic", semantic: "Semantic",
  procedural: "Procedural", reflective: "Reflective",
};

export default function PlaygroundPage() {
  const qc = useQueryClient();

  const [userId, setUserId] = useState("alice");
  const [content, setContent] = useState("");
  const [writeType, setWriteType] = useState<MemoryType>("semantic");
  const [query, setQuery] = useState("");
  const [searchResp, setSearchResp] = useState<SearchResponse | null>(null);

  const statsQ = useQuery({
    queryKey: ["stats", userId],
    queryFn: () => getStats(userId),
  });

  const writeMut = useMutation({
    mutationFn: () => writeMemory({ user_id: userId, content, type: writeType }),
    onSuccess: () => {
      setContent("");
      qc.invalidateQueries({ queryKey: ["stats", userId] });
    },
  });

  const searchMut = useMutation({
    mutationFn: () => searchMemories({ user_id: userId, query, top_k: 5 }),
    onSuccess: (data) => setSearchResp(data),
  });

  const forgetMut = useMutation({
    mutationFn: () => forgetUser(userId),
    onSuccess: () => {
      setSearchResp(null);
      qc.invalidateQueries({ queryKey: ["stats", userId] });
    },
  });

  const stats = statsQ.data;
  const counts = stats?.counts || ({} as Record<MemoryType, number>);
  const profileLoaded = !!stats?.profile?.profile?.one_liner;
  const triples = stats?.triples || [];
  const totalCount = useMemo(
    () => Object.values(counts).reduce((a, b) => a + (b || 0), 0),
    [counts]
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Playground</h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            亲手写入记忆, 看 5 类记忆累积, 实时观察 4 信号 Hybrid Recall 决策过程
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-zinc-500">User ID:</span>
          <Input
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            className="h-8 w-32"
            placeholder="alice"
          />
          <Button
            variant="outline"
            size="sm"
            disabled={forgetMut.isPending}
            onClick={() => {
              if (confirm(`确定要清空用户 "${userId}" 的所有记忆吗?`)) {
                forgetMut.mutate();
              }
            }}
          >
            {forgetMut.isPending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Trash2 className="h-3 w-3" />
            )}
            重置
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* ── 左:写入面板 ───────────────────────────── */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Send className="h-4 w-4 text-emerald-600" /> 写入记忆
            </CardTitle>
            <CardDescription className="text-xs">
              {writeType === "semantic"
                ? "走 SEMANTIC: LLM 自动抽 fact 进 KG + 冲突仲裁"
                : writeType === "episodic"
                ? "走 EPISODIC: 时序事件 + 异步触发 Semantic 抽取"
                : "走 WORKING: 当前会话短期上下文, FIFO 淘汰"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-1">
              {(["semantic", "episodic", "working"] as MemoryType[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setWriteType(t)}
                  className={cn(
                    "rounded px-2 py-1 text-xs transition-colors",
                    writeType === t
                      ? TYPE_COLORS[t] + " font-medium"
                      : "text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                  )}
                >
                  {TYPE_LABELS[t]}
                </button>
              ))}
            </div>
            <Textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="比如: 我对花生过敏 / 我现在住在杭州"
              className="min-h-[100px]"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                  if (content.trim()) writeMut.mutate();
                }
              }}
            />
            <Button
              onClick={() => writeMut.mutate()}
              disabled={!content.trim() || writeMut.isPending}
              className="w-full"
            >
              {writeMut.isPending ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" /> 写入中
                </>
              ) : (
                <>
                  <Send className="h-3 w-3" /> 写入 (Ctrl/Cmd + Enter)
                </>
              )}
            </Button>
            {writeMut.data?.arbitration && (
              <div className="rounded border border-amber-200 bg-amber-50 p-2 text-xs dark:border-amber-900 dark:bg-amber-950/30">
                <div className="mb-1 flex items-center gap-1">
                  <Sparkles className="h-3 w-3 text-amber-600" />
                  <span className="font-medium text-amber-900 dark:text-amber-200">
                    触发冲突仲裁: {writeMut.data.arbitration.action.toUpperCase()}
                  </span>
                </div>
                <p className="text-amber-700 dark:text-amber-300">
                  {writeMut.data.arbitration.reasoning}
                </p>
              </div>
            )}
            {writeMut.error && (
              <div className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/30">
                {(writeMut.error as Error).message}
              </div>
            )}

            <Separator />
            <div className="space-y-1">
              <div className="text-xs font-medium text-zinc-500 dark:text-zinc-400">快捷模板</div>
              <div className="space-y-1">
                {TEMPLATES.map((t, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      setContent(t.content);
                      setWriteType(t.type);
                    }}
                    className="block w-full rounded px-2 py-1.5 text-left text-xs text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                  >
                    <Badge variant="secondary" className="mr-1 text-[10px]">
                      {TYPE_LABELS[t.type]}
                    </Badge>
                    {t.content}
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ── 中:5 类记忆看板 + KG 图 ───────────────── */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">记忆看板</CardTitle>
            <CardDescription className="text-xs">
              共 {totalCount} 条 / KG {triples.length} 条事实 / 仲裁 {stats?.arbitration_count || 0} 次
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-5 gap-1">
              {(Object.keys(TYPE_LABELS) as MemoryType[]).map((t) => (
                <div
                  key={t}
                  className={cn("rounded-lg p-2 text-center", TYPE_COLORS[t])}
                >
                  <div className="text-lg font-bold tabular-nums">{counts[t] || 0}</div>
                  <div className="text-[10px] opacity-75">{TYPE_LABELS[t]}</div>
                </div>
              ))}
            </div>

            {profileLoaded && (
              <div className="rounded border border-rose-200 bg-rose-50 p-2 text-xs dark:border-rose-900 dark:bg-rose-950/30">
                <div className="mb-0.5 flex items-center gap-1 text-rose-700 dark:text-rose-300">
                  <Sparkles className="h-3 w-3" />
                  <span className="font-medium">Reflective Profile</span>
                </div>
                <p className="text-rose-900 dark:text-rose-200">
                  {stats?.profile?.profile?.one_liner}
                </p>
                {!!stats?.profile?.profile?.constraints?.length && (
                  <p className="mt-1 text-[10px] text-rose-700 dark:text-rose-300">
                    禁忌: {stats?.profile?.profile?.constraints?.join(", ")}
                  </p>
                )}
              </div>
            )}

            <Separator />
            <div>
              <div className="mb-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                KG 知识图谱 ({triples.length} 条 user 事实)
              </div>
              <KgGraph triples={triples} />
            </div>
          </CardContent>
        </Card>

        {/* ── 右:召回 + 4 信号分数 ───────────────── */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Search className="h-4 w-4 text-emerald-600" /> Hybrid Recall
            </CardTitle>
            <CardDescription className="text-xs">
              4 信号融合: 向量 + 时间衰减 + 图扩展 + 重要度
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="比如: 用户能吃花生吗"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && query.trim()) searchMut.mutate();
                }}
              />
              <Button
                onClick={() => searchMut.mutate()}
                disabled={!query.trim() || searchMut.isPending}
              >
                {searchMut.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Search className="h-3 w-3" />
                )}
              </Button>
            </div>

            {searchResp && (
              <div className="text-xs text-zinc-500 dark:text-zinc-400">
                latency: <b>{searchResp.latency_ms}ms</b> · 返回 {searchResp.results.length} 条
              </div>
            )}

            {searchResp?.results.length === 0 && (
              <div className="rounded border border-dashed border-zinc-300 p-4 text-center text-xs text-zinc-500 dark:border-zinc-700">
                <div className="font-medium text-zinc-600 dark:text-zinc-300">未召回到相关记忆</div>
                <div className="mt-1">
                  此 user_id 下没有 final_score ≥ 0.55 的记忆
                  <br />
                  (左侧先写, 或换个相关 query 重试)
                </div>
              </div>
            )}

            <div className="space-y-3">
              {searchResp?.results.map((r) => (
                <div
                  key={`${r.record.id}-${r.rank}`}
                  className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700"
                >
                  <div className="mb-2 flex items-center gap-2 text-xs">
                    <Badge variant="outline" className="font-mono">
                      #{r.rank}
                    </Badge>
                    <Badge className={TYPE_COLORS[r.record.type]} variant="secondary">
                      {TYPE_LABELS[r.record.type]}
                    </Badge>
                    <span className="ml-auto text-zinc-400">tier={r.record.tier}</span>
                  </div>
                  <p className="mb-3 text-sm leading-relaxed">{r.record.content}</p>
                  <ScoreBar signals={r.signals} />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
