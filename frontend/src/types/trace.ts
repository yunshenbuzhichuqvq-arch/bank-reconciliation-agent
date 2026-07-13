/** Frontend types for the tenant-scoped Replay API.

 * Refs: TASK-29.6
 */

import type { StreamEventType } from "./api";

/** Closed replay availability status. */
export type ReplayStatus = "AVAILABLE" | "IN_PROGRESS" | "TRACE_NOT_AVAILABLE";

/** Safe, tenant-stripped span view — never exposes user_id. */
export interface TraceSpanView {
  schema_version: string;
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  task_id: string;
  flow_id: string;
  sequence_no: number;
  span_type: SpanType;
  name: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  status: SpanStatus;
  outcome: string | null;
  attempt: number;
  retry_recovered: boolean;
  recovered_error_type: string | null;
  structured_repair_attempted: boolean | null;
  structured_repair_succeeded: boolean | null;
  model_name: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  cached_calls: number | null;
  result_count: number | null;
  error_type: string | null;
  fallback_reason: string | null;
  evidence_ids: string[];
}

/** Closed span-type enum. */
export type SpanType =
  | "WORKFLOW"
  | "ROUTE"
  | "TOOL"
  | "AGENT"
  | "GUARD"
  | "FINAL"
  | "FALLBACK";

/** Technical execution result. */
export type SpanStatus = "SUCCEEDED" | "FAILED" | "CANCELLED";

/** Condensed per-run summary, most-recent first. */
export interface TraceRunSummary {
  trace_id: string;
  started_at: string;
  status: SpanStatus;
  outcome: string | null;
}

/** Full Replay data payload inside ApiResponse. */
export interface TraceReplayData {
  replay_status: ReplayStatus;
  selected_trace_id: string | null;
  execution_count: number;
  runs: TraceRunSummary[];
  spans: TraceSpanView[];
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

/** Safe projection labels for timeline display. */
export const SPAN_TYPE_LABEL: Record<SpanType, string> = {
  WORKFLOW: "工作流",
  ROUTE: "路由",
  TOOL: "工具",
  AGENT: "Agent",
  GUARD: "安全 Guard",
  FINAL: "最终决策",
  FALLBACK: "Fallback",
};

export const SPAN_STATUS_LABEL: Record<SpanStatus, string> = {
  SUCCEEDED: "成功",
  FAILED: "失败",
  CANCELLED: "已取消",
};

/** trace_span SSE event payload (same shape as TraceSpanView). */
export interface TraceSpanPayload extends TraceSpanView {}

/** Augmented StreamEventType union that includes trace_span (v1.2). */
export type StreamEventTypeV12 = StreamEventType | "trace_span";
