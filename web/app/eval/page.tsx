"use client";

import { useState, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Play,
  Loader2,
  CheckCircle2,
  XCircle,
  TrendingUp,
  BarChart3,
  StopCircle,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, BarChart, Bar, Legend,
} from "recharts";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getEvalHistory, streamEval } from "@/lib/api";
import { cn } from "@/lib/utils";

type Suite = "cn_scenarios" | "longmemeval_cn30";

interface EvalItemRecord {
  index: number;
  name?: string;
  question_id?: string;
  subtype?: string;
  pass: boolean;
  latency_ms: number;
}

interface RunSummary {
  passed: number;
  total: number;
  pass_rate: number;
  by_subtype?: Record<string, { passed: number; total: number }>;
}

const SUITE_LABEL: Record<Suite, string> = {
  cn_scenarios: "cn_scenarios (8 题冲突仲裁)",
  longmemeval_cn30: "LongMemEval-style CN (30 题)",
};

const SUBTYPE_LABEL: Record<string, string> = {
  single_session: "SS 单轮长上下文",
  multi_session: "MS 跨段拼接",
  temporal_reasoning: "TR 时间敏感",
  knowledge_update: "KU 信息更新",
};

export default function EvalPage() {
  const [suite, setSuite] = useState<Suite>("cn_scenarios");
  const [running, setRunning] = useState(false);
  const [items, setItems] = useState<EvalItemRecord[]>([]);
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [total, setTotal] = useState(0);
  const esRef = useRef<EventSource | null>(null);

  // 历史
  const historyQ = useQuery({
    queryKey: ["eval-history", suite, summary?.pass_rate],
    queryFn: () => getEvalHistory(suite, 30),
  });

  const startRun = () => {
    setItems([]);
    setSummary(null);
    setRunning(true);
    setTotal(0);
    const es = streamEval(suite === "longmemeval_cn30" ? "longmemeval" : suite, {
      onStart: (e) => setTotal(e.total),
      onItem: (raw) => {
        const it = raw as unknown as EvalItemRecord;
        setItems((prev) => [...prev, it]);
      },
      onDone: (e) => {
        setSummary(e as RunSummary);
        setRunning(false);
      },
      onError: () => {
        setRunning(false);
      },
    });
    esRef.current = es;
  };

  const stopRun = () => {
    esRef.current?.close();
    esRef.current = null;
    setRunning(false);
  };

  // ── 派生数据 ───────────────────────────────
  const passedCount = items.filter((i) => i.pass).length;
  const passRate = items.length ? (passedCount / items.length) * 100 : 0;

  // 历史趋势数据
  const trendData = useMemo(() => {
    const runs = historyQ.data?.runs || [];
    return runs.map((r, i) => ({
      n: `#${i + 1}`,
      time: r.created_at.slice(5, 16).replace("T", " "),
      score: Math.round(r.score * 100),
    }));
  }, [historyQ.data]);

  // LongMemEval 分维度柱状图
  const subtypeData = useMemo(() => {
    if (!summary?.by_subtype) {
      // 实时从 items 算
      if (items.length === 0) return [];
      const buckets: Record<string, { p: number; t: number }> = {};
      for (const it of items) {
        const k = it.subtype || "default";
        if (!buckets[k]) buckets[k] = { p: 0, t: 0 };
        buckets[k].t++;
        if (it.pass) buckets[k].p++;
      }
      return Object.entries(buckets).map(([k, v]) => ({
        subtype: SUBTYPE_LABEL[k] || k,
        rate: Math.round((v.p / v.t) * 100),
        passed: v.p,
        total: v.t,
      }));
    }
    return Object.entries(summary.by_subtype).map(([k, v]) => ({
      subtype: SUBTYPE_LABEL[k] || k,
      rate: Math.round((v.passed / v.total) * 100),
      passed: v.passed,
      total: v.total,
    }));
  }, [summary, items]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Eval 跑分</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          SSE 流式实时跑分 + 跨版本回归对比 + 分维度准确率
        </p>
      </div>

      {/* Suite 选择 + 跑分按钮 */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-3">
            <Tabs value={suite} onValueChange={(v) => setSuite(v as Suite)}>
              <TabsList>
                <TabsTrigger value="cn_scenarios">cn_scenarios</TabsTrigger>
                <TabsTrigger value="longmemeval_cn30">longmemeval_cn30</TabsTrigger>
              </TabsList>
            </Tabs>
            <div className="text-xs text-zinc-500 dark:text-zinc-400">
              {SUITE_LABEL[suite]}
            </div>
            <div className="ml-auto flex gap-2">
              {running ? (
                <Button variant="outline" onClick={stopRun}>
                  <StopCircle className="h-3 w-3" /> 停止
                </Button>
              ) : (
                <Button onClick={startRun} className="bg-emerald-600 hover:bg-emerald-700">
                  <Play className="h-3 w-3" /> 开始跑分
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 进度 */}
      {(running || items.length > 0) && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              {running && <Loader2 className="h-4 w-4 animate-spin text-emerald-600" />}
              实时进度 {items.length}/{total || "?"}
              {summary && (
                <Badge
                  variant={summary.pass_rate >= 0.8 ? "default" : "secondary"}
                  className="ml-2"
                >
                  最终 {Math.round(summary.pass_rate * 100)}%
                </Badge>
              )}
            </CardTitle>
            <CardDescription>
              当前进度: {passedCount}/{items.length} 通过 ({passRate.toFixed(0)}%)
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* 进度条 */}
            <div className="mb-3">
              <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
                <div
                  className="h-full bg-emerald-500 transition-all duration-300"
                  style={{ width: total ? `${(items.length / total) * 100}%` : "0%" }}
                />
              </div>
            </div>
            {/* 每题实时输出 */}
            <div className="max-h-72 overflow-y-auto rounded-lg border border-zinc-200 bg-zinc-50 p-2 font-mono text-xs dark:border-zinc-700 dark:bg-zinc-900">
              {items.length === 0 && running && (
                <div className="text-center text-zinc-400 py-4">
                  等待第一题完成... 平均每题 5-30s (LLM 抽取+召回)
                </div>
              )}
              {items.map((it) => (
                <div
                  key={it.index}
                  className={cn(
                    "flex items-center gap-2 py-1",
                    it.pass ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"
                  )}
                >
                  {it.pass ? (
                    <CheckCircle2 className="h-3 w-3 shrink-0" />
                  ) : (
                    <XCircle className="h-3 w-3 shrink-0" />
                  )}
                  <span className="w-12 shrink-0 tabular-nums">[{String(it.index).padStart(2, "0")}/{total}]</span>
                  <span className="flex-1 truncate text-zinc-700 dark:text-zinc-300">
                    {it.name || it.question_id} {it.subtype && <span className="text-zinc-400">({SUBTYPE_LABEL[it.subtype] || it.subtype})</span>}
                  </span>
                  <span className="shrink-0">{it.pass ? "PASS" : "FAIL"}</span>
                  <span className="w-16 shrink-0 text-right tabular-nums text-zinc-400">
                    {it.latency_ms.toFixed(0)}ms
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 分维度柱状图 */}
        {subtypeData.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-violet-600" /> 分维度准确率
              </CardTitle>
              <CardDescription>当前一次跑分按子类型聚合</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={subtypeData} layout="vertical" margin={{ left: 90 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
                  <XAxis type="number" domain={[0, 100]} unit="%" />
                  <YAxis dataKey="subtype" type="category" width={90} />
                  <Tooltip
                    formatter={(v, _n, p) => {
                      const data = p?.payload as { passed: number; total: number };
                      return [`${v}% (${data?.passed}/${data?.total})`, "通过率"];
                    }}
                  />
                  <Bar dataKey="rate" fill="#10b981" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}

        {/* 历史趋势 */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-emerald-600" /> 历史跑分趋势
            </CardTitle>
            <CardDescription>
              {SUITE_LABEL[suite]} · 共 {trendData.length} 次跑分
            </CardDescription>
          </CardHeader>
          <CardContent>
            {trendData.length === 0 ? (
              <div className="flex h-[280px] items-center justify-center text-sm text-zinc-400">
                暂无历史 — 点 "开始跑分" 后会自动入库
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
                  <XAxis dataKey="n" />
                  <YAxis domain={[0, 100]} unit="%" />
                  <Tooltip
                    labelFormatter={(_l, p) =>
                      p[0] ? `${p[0].payload.n} (${p[0].payload.time})` : ""
                    }
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="score"
                    name="总分"
                    stroke="#10b981"
                    strokeWidth={2}
                    dot={{ fill: "#10b981", r: 4 }}
                    activeDot={{ r: 6 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
