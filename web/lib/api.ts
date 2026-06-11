/**
 * 与 MemoCortex FastAPI 后端通信的客户端封装.
 *
 * 环境变量 NEXT_PUBLIC_API_BASE 控制后端地址:
 *   - 本机开发: http://localhost:8765 (默认)
 *   - 线上部署: https://memocortex-api.your-domain.com
 *
 * 所有方法都 throw on non-2xx, 上层用 try/catch 或 TanStack Query 的 error 拿.
 */

import type {
  EntityResponse,
  EvalRun,
  ProfileResponse,
  ScenarioMeta,
  ScenarioRunResponse,
  SearchResponse,
  UserStatsResponse,
  WriteResponse,
  MemoryType,
  ConflictAction,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8765";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail || JSON.stringify(body);
    } catch {
      detail = (await res.text()) || detail;
    }
    throw new Error(`[${path}] ${detail}`);
  }
  return res.json() as Promise<T>;
}

// ── Health ──────────────────────────────────────────────────────────
export async function getHealth() {
  return http<{ status: string; version: string; data_dir: string }>("/health");
}

// ── Memories ────────────────────────────────────────────────────────
export interface WriteParams {
  user_id: string;
  content: string;
  type?: MemoryType;
  session_id?: string;
  importance?: number;
  tags?: string[];
  structured?: Record<string, unknown>;
}

export async function writeMemory(p: WriteParams): Promise<WriteResponse> {
  return http<WriteResponse>("/v1/memories", {
    method: "POST",
    body: JSON.stringify({ type: "episodic", ...p }),
  });
}

export interface SearchParams {
  user_id: string;
  query: string;
  types?: MemoryType[] | null;
  top_k?: number;
  session_id?: string;
}

export async function searchMemories(p: SearchParams): Promise<SearchResponse> {
  return http<SearchResponse>("/v1/memories/search", {
    method: "POST",
    body: JSON.stringify(p),
  });
}

export async function forgetUser(user_id: string): Promise<unknown> {
  return http("/v1/memories/forget", {
    method: "POST",
    body: JSON.stringify({ user_id, confirm: true }),
  });
}

// ── Profile / Entities ──────────────────────────────────────────────
export async function getProfile(
  user_id: string,
  auto_refresh = false
): Promise<ProfileResponse> {
  return http<ProfileResponse>(
    `/v1/users/${encodeURIComponent(user_id)}/profile?auto_refresh=${auto_refresh}`
  );
}

export async function getEntities(
  user_id: string,
  entity = "user"
): Promise<EntityResponse> {
  return http<EntityResponse>(
    `/v1/users/${encodeURIComponent(user_id)}/entities/${encodeURIComponent(entity)}`
  );
}

// ── Stats ───────────────────────────────────────────────────────────
export async function getStats(
  user_id: string,
  recent_n = 5
): Promise<UserStatsResponse> {
  return http<UserStatsResponse>(
    `/v1/stats/${encodeURIComponent(user_id)}?recent_n=${recent_n}`
  );
}

// ── Demo ────────────────────────────────────────────────────────────
export async function listScenarios(): Promise<{ scenarios: ScenarioMeta[] }> {
  return http("/v1/demo/scenarios");
}

export async function runScenario(
  scenario: string
): Promise<ScenarioRunResponse> {
  return http<ScenarioRunResponse>("/v1/demo/conflict-scenario", {
    method: "POST",
    body: JSON.stringify({ scenario }),
  });
}

// ── Admin / Eval ────────────────────────────────────────────────────
export async function getEvalHistory(
  suite: string,
  limit = 20
): Promise<{ suite: string; runs: EvalRun[] }> {
  return http(
    `/admin/eval/history/${encodeURIComponent(suite)}?limit=${limit}`
  );
}

export async function getArbitrations(user_id: string, limit = 50) {
  return http<{
    user_id: string;
    count: number;
    items: Array<{
      action: ConflictAction;
      reasoning: string;
      old_value?: string | null;
      new_value: string;
      subject: string;
      predicate: string;
      created_at: string;
    }>;
  }>(
    `/admin/arbitrations/${encodeURIComponent(user_id)}?limit=${limit}`
  );
}

// ── Signals & Pattern Miner (Phase 2) ───────────────────────────────
export type SignalType =
  | "regenerate_request"
  | "explicit_correction"
  | "format_preference"
  | "tool_selection"
  | "positive_feedback"
  | "topic_pivot";

export interface TrackSignalParams {
  user_id: string;
  signal_type: SignalType;
  context_tags?: string[];
  memory_ids_in_context?: string[];
  session_id?: string;
  extra?: Record<string, unknown>;
}

export async function trackSignal(p: TrackSignalParams) {
  return http<{ signal_id: number; status: string }>("/v1/signals/track", {
    method: "POST",
    body: JSON.stringify(p),
  });
}

export async function listSignals(user_id: string, limit = 50) {
  return http<{
    user_id: string;
    count: number;
    items: Array<{
      id: number;
      signal_type: SignalType;
      context_tags: string[];
      memory_ids_in_context: string[];
      session_id?: string;
      extra: Record<string, unknown>;
      created_at: string;
    }>;
  }>(`/v1/signals/${encodeURIComponent(user_id)}?limit=${limit}`);
}

export interface MinedImplicit {
  id: string;
  content: string;
  confidence: number;
  keywords: string[];
  evidence_count: number;
}

export async function minePatterns(user_id: string, window_days = 14) {
  return http<{
    user_id: string;
    window_days: number;
    new_implicit_count: number;
    new_records: MinedImplicit[];
  }>(`/admin/mine_patterns/${encodeURIComponent(user_id)}?window_days=${window_days}`, {
    method: "POST",
  });
}

// ── SSE Eval Run ────────────────────────────────────────────────────
/**
 * 用 EventSource 拿流式 eval 跑分.
 * 调用方:
 *   const es = streamEval('cn_scenarios', { onItem, onDone, onError })
 *   // 取消订阅: es.close()
 */
export function streamEval(
  suite: "cn_scenarios" | "longmemeval" | "longmemeval_cn30",
  handlers: {
    onStart?: (e: { suite: string; total: number }) => void;
    onItem?: (e: Record<string, unknown>) => void;
    onDone?: (e: { passed: number; total: number; pass_rate: number }) => void;
    onError?: (err: Event | Error) => void;
  }
): EventSource {
  const url = `${API_BASE}/admin/eval/run?suite=${encodeURIComponent(suite)}`;
  const es = new EventSource(url);

  es.addEventListener("start", (e) => {
    try {
      handlers.onStart?.(JSON.parse((e as MessageEvent).data));
    } catch (err) {
      handlers.onError?.(err as Error);
    }
  });
  es.addEventListener("item", (e) => {
    try {
      handlers.onItem?.(JSON.parse((e as MessageEvent).data));
    } catch (err) {
      handlers.onError?.(err as Error);
    }
  });
  es.addEventListener("done", (e) => {
    try {
      handlers.onDone?.(JSON.parse((e as MessageEvent).data));
    } finally {
      es.close();
    }
  });
  es.addEventListener("error", (e) => {
    handlers.onError?.(e);
  });

  return es;
}
