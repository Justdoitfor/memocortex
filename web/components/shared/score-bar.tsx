"use client";

import { motion } from "framer-motion";
import type { RecallSignals } from "@/lib/types";

interface ScoreBarProps {
  signals: RecallSignals;
  weights?: { vector: number; temporal: number; graph: number; importance: number };
}

const DEFAULT_WEIGHTS = { vector: 0.4, temporal: 0.2, graph: 0.2, importance: 0.2 };

const SIGNAL_COLORS = {
  vector: "bg-emerald-500",
  temporal: "bg-sky-500",
  graph: "bg-violet-500",
  importance: "bg-amber-500",
};

/**
 * 单条召回结果的 4 信号融合分数可视化.
 * 每个信号一行水平条, 末尾显示 (信号原值 × 权重 = 贡献分).
 */
export function ScoreBar({ signals, weights = DEFAULT_WEIGHTS }: ScoreBarProps) {
  const items = [
    { key: "vector" as const, label: "向量相似", val: signals.vector_sim, w: weights.vector },
    { key: "temporal" as const, label: "时间衰减", val: signals.temporal_decay, w: weights.temporal },
    { key: "graph" as const, label: "BM25", val: signals.graph_proximity, w: weights.graph },
    { key: "importance" as const, label: "重要度", val: signals.importance, w: weights.importance },
  ];

  return (
    <div className="space-y-1.5">
      {items.map((it) => {
        const pct = Math.max(0, Math.min(1, it.val)) * 100;
        const contrib = it.val * it.w;
        return (
          <div key={it.key} className="flex items-center gap-2 text-xs">
            <span className="w-16 shrink-0 text-zinc-500 dark:text-zinc-400">{it.label}</span>
            <div className="relative flex-1 h-2 rounded-full bg-zinc-100 dark:bg-zinc-800 overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${pct}%` }}
                transition={{ duration: 0.4, ease: "easeOut" }}
                className={`absolute inset-y-0 left-0 ${SIGNAL_COLORS[it.key]}`}
              />
            </div>
            <span className="w-32 shrink-0 text-right tabular-nums text-zinc-500 dark:text-zinc-400">
              {it.val.toFixed(2)} × {it.w.toFixed(1)} = <b className="text-zinc-700 dark:text-zinc-300">{contrib.toFixed(3)}</b>
            </span>
          </div>
        );
      })}
      <div className="mt-2 flex items-center justify-between border-t border-zinc-200 pt-2 text-sm dark:border-zinc-700">
        <span className="text-zinc-500 dark:text-zinc-400">final_score</span>
        <span className="font-mono font-semibold text-emerald-700 dark:text-emerald-400">
          {signals.final_score.toFixed(4)}
        </span>
      </div>
    </div>
  );
}
