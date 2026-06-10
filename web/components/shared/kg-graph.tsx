"use client";

import { useMemo } from "react";
import ReactFlow, {
  Node, Edge, Background, Controls, MarkerType,
  type NodeTypes,
} from "reactflow";
import "reactflow/dist/style.css";

interface KgGraphProps {
  triples: { subject: string; predicate: string; object: string }[];
  className?: string;
}

/**
 * KG 三元组可视化 — 把 (subject, predicate, object) 列表渲染成
 * 节点 + 边的有向图.
 */
export function KgGraph({ triples }: KgGraphProps) {
  const { nodes, edges } = useMemo(() => buildGraph(triples), [triples]);

  if (triples.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-zinc-300 text-sm text-zinc-400 dark:border-zinc-700">
        暂无 KG 事实 — 试试在左侧写一条 "我对花生过敏"
      </div>
    );
  }

  return (
    <div className="h-[420px] rounded-lg border border-zinc-200 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

function buildGraph(triples: { subject: string; predicate: string; object: string }[]): {
  nodes: Node[];
  edges: Edge[];
} {
  const nodeMap = new Map<string, Node>();
  const edges: Edge[] = [];

  // 圆形布局 — 中心放 user, 其他实体围一圈
  const objects = Array.from(new Set(triples.map((t) => t.object)));
  const subjects = Array.from(new Set(triples.map((t) => t.subject)));
  const centerCandidates = subjects.length === 1 ? subjects : ["user", ...subjects];
  const center = centerCandidates[0];

  nodeMap.set(center, {
    id: center,
    position: { x: 0, y: 0 },
    data: { label: center },
    style: {
      background: "#10b981",
      color: "#fff",
      border: "2px solid #047857",
      borderRadius: 12,
      padding: "8px 14px",
      fontWeight: 600,
      fontSize: 13,
    },
  });

  const N = objects.length || 1;
  const R = 180;
  objects.forEach((obj, i) => {
    if (obj === center) return;
    const theta = (2 * Math.PI * i) / N - Math.PI / 2;
    nodeMap.set(obj, {
      id: obj,
      position: { x: R * Math.cos(theta), y: R * Math.sin(theta) },
      data: { label: obj },
      style: {
        background: "#fff",
        border: "2px solid #a78bfa",
        borderRadius: 8,
        padding: "6px 12px",
        fontSize: 12,
        color: "#18181b",
      },
    });
  });
  // 其他 subject 若不在 nodeMap, 加上
  subjects.forEach((s) => {
    if (!nodeMap.has(s)) {
      nodeMap.set(s, {
        id: s,
        position: { x: -R, y: 0 },
        data: { label: s },
        style: {
          background: "#fff",
          border: "2px solid #71717a",
          borderRadius: 8,
          padding: "6px 12px",
          fontSize: 12,
          color: "#18181b",
        },
      });
    }
  });

  triples.forEach((t, idx) => {
    edges.push({
      id: `e-${idx}-${t.subject}-${t.predicate}-${t.object}`,
      source: t.subject,
      target: t.object,
      label: t.predicate,
      labelStyle: { fontSize: 11, fill: "#52525b", fontWeight: 500 },
      labelBgStyle: { fill: "#f4f4f5", fillOpacity: 0.9 },
      labelBgPadding: [4, 2],
      labelBgBorderRadius: 4,
      style: { stroke: "#a78bfa", strokeWidth: 1.5 },
      markerEnd: { type: MarkerType.ArrowClosed, color: "#a78bfa" },
      type: "default",
    });
  });

  return { nodes: Array.from(nodeMap.values()), edges };
}
