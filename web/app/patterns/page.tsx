"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Loader2, Send, Sparkles, ListChecks, BrainCircuit, AlertCircle,
  RotateCcw, MessageSquareWarning, FileEdit, Heart, GitFork, MessagesSquare,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { listSignals, minePatterns, trackSignal, type SignalType } from "@/lib/api";
import { cn } from "@/lib/utils";

const SIGNAL_META: Record<SignalType, { label: string; icon: typeof RotateCcw; color: string; desc: string }> = {
  regenerate_request: {
    label: "重新生成", icon: RotateCcw,
    color: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
    desc: "用户对回答不满意, 要求重新生成",
  },
  explicit_correction: {
    label: "明确纠正", icon: MessageSquareWarning,
    color: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
    desc: "用户主动纠正信息",
  },
  format_preference: {
    label: "格式偏好", icon: FileEdit,
    color: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
    desc: "用户改变了回答格式 (长/短/代码/列表)",
  },
  tool_selection: {
    label: "工具选择", icon: ListChecks,
    color: "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300",
    desc: "用户选择了某个工具的结果",
  },
  positive_feedback: {
    label: "正向反馈", icon: Heart,
    color: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
    desc: "用户表示满意 / 点赞",
  },
  topic_pivot: {
    label: "话题转换", icon: GitFork,
    color: "bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-900/30 dark:text-fuchsia-300",
    desc: "用户中途转换话题",
  },
};

const QUICK_TEMPLATES: { signal_type: SignalType; tags: string[]; label: string }[] = [
  { signal_type: "regenerate_request", tags: ["code_review"], label: "代码评审场景 - 重新生成 ×1" },
  { signal_type: "regenerate_request", tags: ["code_review"], label: "代码评审场景 - 重新生成 ×1" },
  { signal_type: "regenerate_request", tags: ["code_review"], label: "代码评审场景 - 重新生成 ×1" },
  { signal_type: "format_preference", tags: ["writing"], label: "写作场景 - 偏好简短" },
  { signal_type: "format_preference", tags: ["writing"], label: "写作场景 - 偏好简短" },
  { signal_type: "format_preference", tags: ["writing"], label: "写作场景 - 偏好简短" },
  { signal_type: "positive_feedback", tags: ["code_review"], label: "代码评审 - 正向反馈" },
];

export default function PatternsPage() {
  const qc = useQueryClient();
  const [userId, setUserId] = useState("alice");
  const [windowDays, setWindowDays] = useState(14);

  const signalsQ = useQuery({
    queryKey: ["signals", userId],
    queryFn: () => listSignals(userId, 100),
  });

  const trackMut = useMutation({
    mutationFn: (p: { signal_type: SignalType; tags: string[] }) =>
      trackSignal({
        user_id: userId,
        signal_type: p.signal_type,
        context_tags: p.tags,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["signals", userId] }),
  });

  const mineMut = useMutation({
    mutationFn: () => minePatterns(userId, windowDays),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["signals", userId] }),
  });

  const signals = signalsQ.data?.items || [];
  // 按 signal_type + tags 聚合
  const grouped = signals.reduce<Record<string, { count: number; signal_type: SignalType; tags: string[] }>>((acc, s) => {
    const tagsKey = [...s.context_tags].sort().join("+");
    const key = `${s.signal_type}|${tagsKey}`;
    if (!acc[key]) acc[key] = { count: 0, signal_type: s.signal_type, tags: s.context_tags };
    acc[key].count++;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <BrainCircuit className="h-7 w-7 text-fuchsia-600" />
            隐式行为模式挖掘
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            上报用户行为信号 → Pattern Miner 周期归纳 → 生成 Implicit 记忆 (参考 Honcho dialectic pattern inference)
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
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* 左:6 类 signal 上报 */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Send className="h-4 w-4 text-fuchsia-600" /> 上报行为信号
            </CardTitle>
            <CardDescription className="text-xs">
              点击下方按钮模拟 Agent 上报用户行为
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {(Object.entries(SIGNAL_META) as [SignalType, typeof SIGNAL_META["regenerate_request"]][]).map(([st, meta]) => {
              const Icon = meta.icon;
              return (
                <button
                  key={st}
                  onClick={() => trackMut.mutate({ signal_type: st, tags: ["demo"] })}
                  disabled={trackMut.isPending}
                  className={cn(
                    "w-full flex items-start gap-2 rounded-lg border border-zinc-200 dark:border-zinc-700 p-2 text-left hover:bg-zinc-50 dark:hover:bg-zinc-900 transition-colors disabled:opacity-50",
                  )}
                >
                  <div className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded", meta.color)}>
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium">{meta.label}</div>
                    <div className="text-[10px] text-zinc-500 dark:text-zinc-400 truncate">{meta.desc}</div>
                  </div>
                </button>
              );
            })}

            <Separator className="my-2" />
            <div className="text-xs font-medium text-zinc-500 mb-1">快捷场景</div>
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              disabled={trackMut.isPending}
              onClick={async () => {
                // 一键打 3 次代码评审 regenerate
                for (let i = 0; i < 3; i++) {
                  await trackMut.mutateAsync({ signal_type: "regenerate_request", tags: ["code_review"] });
                }
              }}
            >
              代码评审场景 × 3 次重新生成
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              disabled={trackMut.isPending}
              onClick={async () => {
                for (let i = 0; i < 3; i++) {
                  await trackMut.mutateAsync({ signal_type: "format_preference", tags: ["writing"] });
                }
              }}
            >
              写作场景 × 3 次格式偏好
            </Button>
          </CardContent>
        </Card>

        {/* 中:信号聚合 */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <ListChecks className="h-4 w-4 text-violet-600" /> 信号聚合 ({signals.length} 条)
            </CardTitle>
            <CardDescription className="text-xs">
              按 (signal_type, context_tags) 分组. ≥ 3 次会被 Pattern Miner 挖掘
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(grouped).length === 0 ? (
              <div className="rounded border border-dashed border-zinc-300 p-4 text-center text-xs text-zinc-400 dark:border-zinc-700">
                还没有信号 — 点左侧"快捷场景"模拟
              </div>
            ) : (
              Object.values(grouped).map((g) => {
                const meta = SIGNAL_META[g.signal_type];
                const ready = g.count >= 3;
                const Icon = meta.icon;
                return (
                  <div
                    key={`${g.signal_type}+${g.tags.join("+")}`}
                    className={cn(
                      "rounded-lg p-2 text-xs border",
                      ready
                        ? "border-fuchsia-400 bg-fuchsia-50 dark:bg-fuchsia-950/30"
                        : "border-zinc-200 dark:border-zinc-700"
                    )}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <div className={cn("flex h-5 w-5 items-center justify-center rounded", meta.color)}>
                        <Icon className="h-3 w-3" />
                      </div>
                      <span className="font-medium">{meta.label}</span>
                      <Badge variant={ready ? "default" : "secondary"} className="ml-auto tabular-nums">
                        {g.count}/3
                      </Badge>
                    </div>
                    <div className="text-zinc-500 dark:text-zinc-400">
                      tags: {g.tags.length > 0 ? g.tags.map((t) => `#${t}`).join(" ") : "(无)"}
                    </div>
                    {ready && (
                      <div className="mt-1 text-fuchsia-700 dark:text-fuchsia-400 text-[10px]">
                        ✓ 达到挖掘阈值, 可触发 Pattern Miner
                      </div>
                    )}
                  </div>
                );
              })
            )}

            <Separator className="my-2" />
            <Button
              className="w-full bg-fuchsia-600 hover:bg-fuchsia-700"
              disabled={mineMut.isPending}
              onClick={() => mineMut.mutate()}
            >
              {mineMut.isPending ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" /> LLM 挖掘中... (5-30s)
                </>
              ) : (
                <>
                  <Sparkles className="h-3 w-3" /> 触发 Pattern Miner
                </>
              )}
            </Button>
            <div className="text-[10px] text-zinc-400 text-center">
              window_days: {windowDays} 天 · 阈值 ≥ 3 次
            </div>
          </CardContent>
        </Card>

        {/* 右:Implicit 挖掘结果 */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-fuchsia-600" /> Implicit Memory 挖掘结果
            </CardTitle>
            <CardDescription className="text-xs">
              LLM 归纳出的隐式偏好 (写入为 IMPLICIT 类型, source=inferred)
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {mineMut.error && (
              <div className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/30">
                {(mineMut.error as Error).message}
              </div>
            )}
            {!mineMut.data && !mineMut.isPending && (
              <div className="rounded border border-dashed border-zinc-300 p-4 text-center text-xs text-zinc-400 dark:border-zinc-700">
                <MessagesSquare className="mx-auto mb-1 h-5 w-5" />
                先在中间累积 ≥ 3 次同类信号, 然后点"触发 Pattern Miner"
              </div>
            )}
            {mineMut.data && (
              <>
                <div className="text-xs text-zinc-500">
                  本次新增 <b>{mineMut.data.new_implicit_count}</b> 条 Implicit 记忆
                  {mineMut.data.new_implicit_count === 0 && (
                    <span className="ml-1 text-zinc-400">(可能已存在 / 未达阈值)</span>
                  )}
                </div>
                {mineMut.data.new_records.map((r) => (
                  <div
                    key={r.id}
                    className="rounded-lg border-l-4 border-fuchsia-500 bg-fuchsia-50 p-3 text-xs dark:bg-fuchsia-950/30"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Sparkles className="h-3 w-3 text-fuchsia-600" />
                      <span className="font-medium text-fuchsia-900 dark:text-fuchsia-200">
                        Implicit
                      </span>
                      <Badge variant="outline" className="font-mono ml-auto">
                        conf {(r.confidence * 100).toFixed(0)}%
                      </Badge>
                    </div>
                    <p className="text-sm leading-relaxed text-fuchsia-900 dark:text-fuchsia-100">
                      {r.content}
                    </p>
                    {r.keywords.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {r.keywords.map((k) => (
                          <Badge key={k} variant="secondary" className="text-[10px]">
                            #{k}
                          </Badge>
                        ))}
                      </div>
                    )}
                    <div className="mt-1 text-[10px] text-fuchsia-700 dark:text-fuchsia-300">
                      证据 {r.evidence_count} 条 · ID {r.id.slice(0, 8)}
                    </div>
                  </div>
                ))}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 底部:原始 signals 列表 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">原始信号 (最近 100 条)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="max-h-48 overflow-y-auto space-y-1 text-xs font-mono">
            {signals.length === 0 && (
              <div className="text-center text-zinc-400 py-4">暂无信号</div>
            )}
            {signals.map((s) => {
              const meta = SIGNAL_META[s.signal_type];
              return (
                <div key={s.id} className="flex items-center gap-2 py-0.5">
                  <span className="text-zinc-400 tabular-nums w-32 shrink-0">
                    {s.created_at.slice(11, 19)}
                  </span>
                  <Badge variant="outline" className={cn("text-[10px]", meta.color)}>
                    {meta.label}
                  </Badge>
                  <span className="text-zinc-600 dark:text-zinc-400 truncate">
                    {s.context_tags.length > 0 ? s.context_tags.map((t) => `#${t}`).join(" ") : "(无标签)"}
                  </span>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Card className="border-fuchsia-200 dark:border-fuchsia-900 bg-fuchsia-50/50 dark:bg-fuchsia-950/10">
        <CardContent className="p-4 text-xs text-fuchsia-900 dark:text-fuchsia-300">
          <AlertCircle className="inline h-3 w-3 mr-1" />
          <b>Implicit vs Reflective</b>:Reflective 是显式用户画像(从 Semantic facts 聚合,"住北京, 对花生过敏");
          Implicit 是隐式行为偏好(从 signals 挖掘,"在 code review 场景偏好简短回答")。
          两者互补,共同注入 Agent SystemPrompt 让 Agent 更懂你。
        </CardContent>
      </Card>
    </div>
  );
}
