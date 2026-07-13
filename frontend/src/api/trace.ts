import { apiGet } from "./client";
import type { TraceReplayData } from "../types/trace";

/** Fetch a read-only Trace Replay for a tenant's task/flow.

 * The optional `trace_id` selects a specific historical run; omitting it
 * returns the latest execution determined by the backend.
 */
export function fetchTraceReplay(
  taskId: string,
  flowId: string,
  traceId?: string,
): Promise<TraceReplayData> {
  const params: Record<string, unknown> = {};
  if (traceId) {
    params.trace_id = traceId;
  }
  return apiGet<TraceReplayData>(
    `/traces/${encodeURIComponent(taskId)}/flows/${encodeURIComponent(flowId)}`,
    params,
  );
}
