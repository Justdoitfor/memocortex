"use client";

import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

mermaid.initialize({
  startOnLoad: false,
  theme: "default",
  themeVariables: {
    fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
    primaryColor: "#10b981",
    primaryTextColor: "#18181b",
    primaryBorderColor: "#10b981",
    lineColor: "#71717a",
    secondaryColor: "#a78bfa",
    tertiaryColor: "#f4f4f5",
  },
  securityLevel: "loose",
});

export function MermaidDiagram({ chart, id }: { chart: string; id?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!ref.current) return;
      try {
        const renderId = id || `mermaid-${Math.random().toString(36).slice(2)}`;
        const { svg } = await mermaid.render(renderId, chart);
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg;
        }
      } catch (e) {
        if (!cancelled) setErr((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chart, id]);

  if (err) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
        Mermaid render error: {err}
      </div>
    );
  }
  return (
    <div
      ref={ref}
      className="flex w-full justify-center overflow-x-auto [&>svg]:max-w-full"
    />
  );
}
