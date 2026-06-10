"use client";

import { useState, useEffect, useMemo } from "react";
import dynamic from "next/dynamic";
import { useQuery, useMutation } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Loader2,
  Play,
  ChevronRight,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Database,
  Network,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { listScenarios, runScenario } from "@/lib/api";
import type { ConflictAction, ScenarioRunResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const KgGraph = dynamic(
  () => import("@/components/shared/kg-graph").then((m) => m.KgGraph),
  {
    ssr: false,
    loading: () => (
      <div className="h-[300px] animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-900" />
    ),
  }
);

// ── Action 配色 ─────────────────────────────────────────────────────
const ACTION_STYLES: Record<
  ConflictAction,
  { bg: string; text: string; border: string; emoji: string; label: string }
> = {
  replace: {
    bg: "bg-amber-50 dark:bg-amber-950/30",
    text: "text-amber-700 dark:text-amber-300",
    border: "border-amber-400",
    emoji: "🔁",
    label: "REPLACE — 新事实覆盖旧事实",
  },
  merge: {
    bg: "bg-emerald-50 dark:bg-emerald-950/30",
    text: "text-emerald-700 dark:text-emerald-300",
    border: "border-emerald-400",
    emoji: "🤝",
    label: "MERGE — list 字段合并两侧",
  },
  versioned: {
    bg: "bg-sky-50 dark:bg-sky-950/30",
    text: "text-sky-700 dark:text-sky-300",
    border: "border-sky-400",
    emoji: "⏱️",
    label: "VERSIONED — 同时保留, 标 valid_from/until",
  },
  ignore: {
    bg: "bg-zinc-100 dark:bg-zinc-900",
    text: "text-zinc-600 dark:text-zinc-400",
    border: "border-zinc-300 dark:border-zinc-700",
    emoji: "🚫",
    label: "IGNORE — 新事实可疑, 仅记 Episodic",
  },
};

const SCENARIO_ICONS: Record<string, string> = {
  relocation: "🏠",
  allergy_merge: "🥜",
  job_change: "💼",
  phone_upgrade: "📱",
};

export default function ConflictPage() {
  const [selected, setSelected] = useState<string>("relocation");
  const [currentStep, setCurrentStep] = useState(0);
  const [data, setData] = useState<ScenarioRunResponse | null>(null);

  const scenariosQ = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => listScenarios(),
  });

  const runMut = useMutation({
    mutationFn: (scenario: string) => runScenario(scenario),
    onSuccess: (resp) => {
      setData(resp);
      setCurrentStep(0);
    },
  });

  // 自动逐步播放动画 (每 step 之间停 1.6s)
  useEffect(() => {
    if (!data) return;
    if (currentStep >= data.steps.length) return;
    const id = setTimeout(() => setCurrentStep((s) => s + 1), 1600);
    return () => clearTimeout(id);
  }, [data, currentStep]);

  const scenarios = scenariosQ.data?.scenarios || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">冲突仲裁动画</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          点击预设场景, 看 LLM-as-Arbitrator 在用户事实变更时如何做 REPLACE / MERGE
          / VERSIONED / IGNORE 决策 — 全程调用真实 DeepSeek-v4-pro
        </p>
      </div>

      {/* 场景选择 */}
      <div className="flex flex-wrap gap-2">
        {scenariosQ.isLoading && (
          <div className="flex items-center gap-2 text-sm text-zinc-500">
            <Loader2 className="h-3 w-3 animate-spin" /> 加载场景列表...
          </div>
        )}
        {scenarios.map((s) => (
          <Button
            key={s.key}
            variant={selected === s.key ? "default" : "outline"}
            onClick={() => setSelected(s.key)}
            disabled={runMut.isPending}
          >
            <span className="mr-1">{SCENARIO_ICONS[s.key] || "🎬"}</span>
            {s.title}
          </Button>
        ))}
        <Button
          variant="default"
          className="ml-auto bg-emerald-600 hover:bg-emerald-700"
          onClick={() => runMut.mutate(selected)}
          disabled={runMut.isPending || !selected}
        >
          {runMut.isPending ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" />
              LLM 仲裁中... (10-30s)
            </>
          ) : (
            <>
              <Play className="h-3 w-3" /> 跑这个场景
            </>
          )}
        </Button>
      </div>

      {runMut.error && (
        <Card className="border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/30">
          <CardContent className="p-3 text-sm text-red-700 dark:text-red-300">
            后端调用失败: {(runMut.error as Error).message}
            <br />
            <span className="text-xs">提示: 确保后端已启动 (
              <code className="font-mono">make api</code>) 且 .env 配置了 LLM API Key
            </span>
          </CardContent>
        </Card>
      )}

      {data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* 左:时间轴动画 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-emerald-600" />
                {data.title}
              </CardTitle>
              <CardDescription>{data.subtitle}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {data.steps.map((step, idx) => {
                  const isActive = idx <= currentStep;
                  const action = step.arbitration_action;
                  const style = action ? ACTION_STYLES[action] : null;
                  return (
                    <AnimatePresence key={idx}>
                      {isActive && (
                        <motion.div
                          initial={{ opacity: 0, x: -20, height: 0 }}
                          animate={{ opacity: 1, x: 0, height: "auto" }}
                          transition={{ duration: 0.35 }}
                          className="relative"
                        >
                          {/* 时间轴竖线 */}
                          <div className="absolute left-3 top-3 bottom-[-12px] w-px bg-zinc-200 dark:bg-zinc-700" />
                          <div className="relative flex gap-3">
                            {/* 圆点 */}
                            <div
                              className={cn(
                                "z-10 mt-1 h-6 w-6 shrink-0 rounded-full border-2 bg-white dark:bg-zinc-900 flex items-center justify-center text-xs font-bold",
                                isActive
                                  ? "border-emerald-500 text-emerald-600"
                                  : "border-zinc-300 text-zinc-400"
                              )}
                            >
                              {idx + 1}
                            </div>
                            <div className="flex-1 space-y-2 pb-3">
                              <div className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                                t={idx * 1.6}s · 用户输入
                              </div>
                              <Card className="border-zinc-200 dark:border-zinc-700">
                                <CardContent className="p-3 text-sm">
                                  {step.content}
                                </CardContent>
                              </Card>
                              {action && style ? (
                                <motion.div
                                  initial={{ opacity: 0, scale: 0.95 }}
                                  animate={{ opacity: 1, scale: 1 }}
                                  transition={{ delay: 0.4, duration: 0.3 }}
                                  className={cn(
                                    "rounded-lg border-l-4 p-3 text-xs",
                                    style.bg,
                                    style.border
                                  )}
                                >
                                  <div className="mb-1 flex items-center gap-2 font-medium">
                                    <span className="text-base">{style.emoji}</span>
                                    <span className={style.text}>
                                      检测到冲突 → LLM 决策:{" "}
                                      <span className="font-bold">
                                        {action.toUpperCase()}
                                      </span>
                                    </span>
                                  </div>
                                  <div className={cn("italic", style.text)}>
                                    "{step.arbitration_reasoning}"
                                  </div>
                                </motion.div>
                              ) : (
                                <div className="text-xs text-zinc-500 dark:text-zinc-400">
                                  <CheckCircle2 className="mr-1 inline h-3 w-3 text-emerald-500" />
                                  无冲突 — 直接写入 KG
                                </div>
                              )}
                            </div>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  );
                })}

                {currentStep >= data.steps.length && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="border-t border-zinc-200 pt-4 text-sm dark:border-zinc-700"
                  >
                    <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
                      <CheckCircle2 className="h-4 w-4" />
                      <span className="font-medium">动画播放完成</span>
                      <button
                        onClick={() => setCurrentStep(0)}
                        className="ml-auto text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
                      >
                        ↺ 重新播放
                      </button>
                    </div>
                  </motion.div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* 右:最终状态 */}
          <div className="space-y-4">
            {/* KG 现状 */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Network className="h-4 w-4 text-violet-600" /> 最终 KG 状态
                </CardTitle>
                <CardDescription className="text-xs">
                  {data.final_triples.length} 条 user 事实 (按字典序)
                </CardDescription>
              </CardHeader>
              <CardContent>
                <KgGraph triples={data.final_triples} />
              </CardContent>
            </Card>

            {/* 审计日志 */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Database className="h-4 w-4 text-sky-600" /> 仲裁审计日志
                </CardTitle>
                <CardDescription className="text-xs">
                  arbitration_logs 表 — 完全可回滚可解释
                </CardDescription>
              </CardHeader>
              <CardContent>
                {data.arbitrations.length === 0 ? (
                  <div className="text-center text-xs text-zinc-400 py-4">
                    本场景无冲突触发(可能首次写入或都是新增 fact)
                  </div>
                ) : (
                  <div className="space-y-2">
                    {data.arbitrations.map((a, i) => {
                      const style = ACTION_STYLES[a.action];
                      return (
                        <div
                          key={i}
                          className={cn(
                            "rounded-lg border-l-4 p-2 text-xs",
                            style.bg,
                            style.border
                          )}
                        >
                          <div className="mb-1 flex items-center gap-2">
                            <Badge variant="outline" className={cn(style.text, "font-mono")}>
                              {style.emoji} {a.action.toUpperCase()}
                            </Badge>
                            <span className="text-zinc-500">
                              ({a.subject}, <b>{a.predicate}</b>)
                            </span>
                          </div>
                          <div className="font-mono text-[11px] text-zinc-600 dark:text-zinc-400">
                            <span className="line-through opacity-60">
                              {a.old_value || "(空)"}
                            </span>
                            <ChevronRight className="mx-1 inline h-3 w-3" />
                            <span className="font-bold text-emerald-700 dark:text-emerald-400">
                              {a.new_value}
                            </span>
                          </div>
                          <div className={cn("mt-1 italic", style.text)}>
                            "{a.reasoning}"
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Top-3 召回 */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">召回结果 (Top-3)</CardTitle>
                <CardDescription className="text-xs">
                  Hybrid Recall: REPLACE 后旧事实应被新事实顶下去
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {data.final_recall.slice(0, 3).map((r) => (
                  <div
                    key={r.rank}
                    className="rounded border border-zinc-200 p-2 text-xs dark:border-zinc-700"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <Badge variant="outline" className="font-mono">
                        #{r.rank} {r.memory_type}
                      </Badge>
                      <span className="font-mono text-emerald-700 dark:text-emerald-400">
                        {r.final_score.toFixed(3)}
                      </span>
                    </div>
                    <p className="text-zinc-700 dark:text-zinc-300">{r.content}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {!data && !runMut.isPending && (
        <Card className="border-dashed">
          <CardContent className="py-12 text-center text-sm text-zinc-500 dark:text-zinc-400">
            <AlertCircle className="mx-auto mb-2 h-6 w-6 text-zinc-400" />
            选一个场景, 点 "跑这个场景" 按钮 — LLM 会真的调用 DeepSeek 做仲裁,
            <br />
            决策结果以时间轴动画展示
          </CardContent>
        </Card>
      )}
    </div>
  );
}
