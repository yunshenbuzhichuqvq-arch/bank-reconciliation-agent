import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it } from "vitest";

import TraceTimeline from "../src/components/TraceTimeline.vue";
import type { TraceSpanView } from "../src/types/trace";

function _span(overrides: Partial<TraceSpanView> = {}): TraceSpanView {
  return {
    schema_version: "1.0",
    trace_id: "trace-1",
    span_id: "span-1",
    parent_span_id: null,
    task_id: "t1",
    flow_id: "f1",
    sequence_no: 1,
    span_type: "WORKFLOW",
    name: "reconciliation_workflow",
    started_at: "2026-07-01T00:00:00Z",
    ended_at: "2026-07-01T00:00:01Z",
    duration_ms: 1000,
    status: "SUCCEEDED",
    outcome: "PENDING_HUMAN",
    attempt: 1,
    retry_recovered: false,
    recovered_error_type: null,
    structured_repair_attempted: null,
    structured_repair_succeeded: null,
    model_name: null,
    prompt_tokens: null,
    completion_tokens: null,
    cached_calls: null,
    result_count: null,
    error_type: null,
    fallback_reason: null,
    evidence_ids: [],
    ...overrides,
  };
}

async function render(spans: TraceSpanView[]) {
  const app = createSSRApp(TraceTimeline, { spans });
  return renderToString(app);
}

describe("TraceTimeline", () => {
  it("renders span type labels", async () => {
    const html = await render([
      _span({ span_type: "WORKFLOW", name: "root" }),
      _span({
        span_type: "TOOL",
        name: "search_rules",
        span_id: "span-2",
        sequence_no: 2,
        outcome: "RESULT",
        evidence_ids: ["chunk-1"],
      }),
    ]);
    expect(html).toContain("工作流");
    expect(html).toContain("工具");
  });

  it("renders error and fallback fields", async () => {
    const html = await render([
      _span({
        span_type: "AGENT",
        name: "AuditAgent",
        span_id: "span-a",
        status: "FAILED",
        error_type: "schema_invalid",
        fallback_reason: "LLM_STRUCTURED_REPAIR_EXHAUSTED",
      }),
    ]);
    expect(html).toContain("schema_invalid");
    expect(html).toContain("LLM_STRUCTURED_REPAIR_EXHAUSTED");
  });

  it("displays token counts for Agent spans", async () => {
    const html = await render([
      _span({
        span_type: "AGENT",
        name: "AuditAgent",
        span_id: "span-b",
        prompt_tokens: 100,
        completion_tokens: 40,
      }),
    ]);
    expect(html).toContain("100");
    expect(html).toContain("40");
  });

  it("shows evidence IDs or empty placeholder", async () => {
    const withEvidence = await render([
      _span({ evidence_ids: ["rule-001", "case-002"] }),
    ]);
    expect(withEvidence).toContain("rule-001");
    expect(withEvidence).toContain("case-002");

    const without = await render([_span()]);
    expect(without).toContain("无引用");
  });
});
