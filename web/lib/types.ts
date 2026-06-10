/**
 * 类型对齐后端 Pydantic 模型 (app/models.py + app/api/*.py)
 *
 * 注意: 后端字段命名是 snake_case (Pydantic), 前端 fetch 后保持原样使用,
 * 不做 camelCase 转换 — 减少心智负担, 出错时一眼对得上后端日志.
 */

// ── 记忆类型 ─────────────────────────────────────────────────────────
export type MemoryType =
  | "working"
  | "episodic"
  | "semantic"
  | "procedural"
  | "reflective";

export type ConflictAction = "replace" | "merge" | "versioned" | "ignore";

// ── MemoryRecord ─────────────────────────────────────────────────────
export interface MemoryRecord {
  id: string;
  user_id: string;
  session_id?: string | null;
  type: MemoryType;
  content: string;
  structured: Record<string, unknown>;
  importance: number;
  created_at: string;
  last_recalled_at?: string | null;
  recall_count: number;
  tier: string;
  tags: string[];
  source: string;
}

// ── Recall ───────────────────────────────────────────────────────────
export interface RecallSignals {
  vector_sim: number;
  temporal_decay: number;
  graph_proximity: number;
  importance: number;
  final_score: number;
}

export interface RecallResult {
  record: MemoryRecord;
  signals: RecallSignals;
  rank: number;
}

export interface SearchResponse {
  results: RecallResult[];
  latency_ms: number;
  signals_used: string[];
}

// ── Write ────────────────────────────────────────────────────────────
export interface ArbitrationDecision {
  action: ConflictAction;
  reasoning: string;
  confidence: number;
  merged_value?: string | null;
}

export interface WriteResponse {
  memory_id: string;
  routed_type: MemoryType;
  arbitration?: ArbitrationDecision | null;
}

// ── Profile ──────────────────────────────────────────────────────────
export interface UserProfile {
  one_liner?: string;
  facts?: Record<string, string>;
  preferences?: string[];
  constraints?: string[];
  interaction_style?: string;
}

export interface ProfileResponse {
  profile: UserProfile;
  updated_at?: string | null;
}

// ── KG ───────────────────────────────────────────────────────────────
export interface Triple {
  id: string;
  subject: string;
  predicate: string;
  object: string;
  confidence: number;
}

export interface EntityResponse {
  user_id: string;
  entity: string;
  triples: Triple[];
  neighbors: string[];
}

// ── Stats ────────────────────────────────────────────────────────────
export interface UserStatsResponse {
  user_id: string;
  counts: Record<MemoryType, number>;
  recent: Record<MemoryType, MemoryRecord[]>;
  triples: { subject: string; predicate: string; object: string }[];
  profile?: ProfileResponse | null;
  arbitration_count: number;
}

// ── Demo Scenarios ───────────────────────────────────────────────────
export interface ScenarioMeta {
  key: string;
  title: string;
  subtitle: string;
  expected_action: ConflictAction;
  writes_count: number;
}

export interface ScenarioStep {
  index: number;
  content: string;
  memory_id: string;
  arbitration_action?: ConflictAction | null;
  arbitration_reasoning?: string | null;
}

export interface ScenarioTripleOut {
  subject: string;
  predicate: string;
  object: string;
  confidence: number;
}

export interface ScenarioArbitrationOut {
  subject: string;
  predicate: string;
  old_value?: string | null;
  new_value: string;
  action: ConflictAction;
  reasoning: string;
  confidence: number;
}

export interface ScenarioRecallOut {
  rank: number;
  content: string;
  memory_type: MemoryType;
  final_score: number;
  vector_sim: number;
  temporal_decay: number;
  graph_proximity: number;
  importance: number;
}

export interface ScenarioRunResponse {
  scenario: string;
  title: string;
  subtitle: string;
  expected_action: ConflictAction;
  user_id: string;
  steps: ScenarioStep[];
  final_triples: ScenarioTripleOut[];
  final_recall: ScenarioRecallOut[];
  arbitrations: ScenarioArbitrationOut[];
}

// ── Eval ─────────────────────────────────────────────────────────────
export interface EvalRun {
  suite: string;
  score: number;
  details: Record<string, unknown>;
  created_at: string;
}

export interface EvalSseStartEvent {
  suite: string;
  total: number;
}

export interface EvalSseItemEvent {
  index: number;
  id?: string;
  question_id?: string;
  name?: string;
  subtype?: string;
  pass: boolean;
  latency_ms: number;
  top_3: string[];
  checks?: Record<string, unknown>;
}

export interface EvalSseDoneEvent {
  passed: number;
  total: number;
  pass_rate: number;
  by_subtype?: Record<string, { passed: number; total: number }>;
}
