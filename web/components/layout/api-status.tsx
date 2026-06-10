"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { getHealth, API_BASE } from "@/lib/api";

/**
 * 后端健康状态徽章 — 顶部右侧 / 页脚显示后端是否可达, 让用户
 * 一眼知道为什么 demo 卡住 (大概率后端没启).
 */
export function ApiStatus() {
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [version, setVersion] = useState<string>("");

  useEffect(() => {
    let mounted = true;
    const check = async () => {
      try {
        const h = await getHealth();
        if (mounted) {
          setStatus("ok");
          setVersion(h.version);
        }
      } catch {
        if (mounted) setStatus("error");
      }
    };
    check();
    const id = setInterval(check, 15000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, []);

  if (status === "loading") {
    return (
      <Badge variant="secondary" className="gap-1">
        <Loader2 className="h-3 w-3 animate-spin" />
        检查后端...
      </Badge>
    );
  }
  if (status === "ok") {
    return (
      <Badge variant="success" className="gap-1">
        <CheckCircle2 className="h-3 w-3" />
        后端 v{version}
      </Badge>
    );
  }
  return (
    <Badge variant="destructive" className="gap-1" title={`Cannot reach ${API_BASE}`}>
      <AlertCircle className="h-3 w-3" />
      后端不可达
    </Badge>
  );
}
