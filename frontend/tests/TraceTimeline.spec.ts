import { describe, expect, it, vi, afterEach } from "vitest";
import { mount } from "@vue/test-utils";

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

async function mountTimeline(spans: TraceSpanView[]) {
  return mount(TraceTimeline, { props: { spans } });
}

function _stubClipboard() {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  return writeText;
}

describe("TraceTimeline", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders span type labels", async () => {
    const wrapper = await mountTimeline([
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
    expect(wrapper.text()).toContain("工作流");
    expect(wrapper.text()).toContain("工具");
  });

  it("renders error and fallback fields", async () => {
    const wrapper = await mountTimeline([
      _span({
        span_type: "AGENT",
        name: "AuditAgent",
        span_id: "span-a",
        status: "FAILED",
        error_type: "schema_invalid",
        fallback_reason: "LLM_STRUCTURED_REPAIR_EXHAUSTED",
      }),
    ]);
    expect(wrapper.text()).toContain("schema_invalid");
    expect(wrapper.text()).toContain("LLM_STRUCTURED_REPAIR_EXHAUSTED");
  });

  it("displays token counts for Agent spans", async () => {
    const wrapper = await mountTimeline([
      _span({
        span_type: "AGENT",
        name: "AuditAgent",
        span_id: "span-b",
        prompt_tokens: 100,
        completion_tokens: 40,
      }),
    ]);
    expect(wrapper.text()).toContain("100");
    expect(wrapper.text()).toContain("40");
  });

  it("shows evidence IDs or empty placeholder", async () => {
    const withEvidence = await mountTimeline([
      _span({ evidence_ids: ["rule-001", "case-002"] }),
    ]);
    expect(withEvidence.text()).toContain("rule-001");
    expect(withEvidence.text()).toContain("case-002");

    const without = await mountTimeline([_span()]);
    expect(without.text()).toContain("无引用");
  });

  it("evidence copy button copies IDs on click", async () => {
    const writeText = _stubClipboard();
    const wrapper = await mountTimeline([
      _span({ evidence_ids: ["rule-001", "case-002"] }),
    ]);

    const btn = wrapper.find(".timeline__evidence-ids");
    expect(btn.exists()).toBe(true);
    await btn.trigger("click");

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText).toHaveBeenCalledWith("rule-001, case-002");
  });

  it("evidence copy button copies IDs on Enter key", async () => {
    const writeText = _stubClipboard();
    const wrapper = await mountTimeline([
      _span({ evidence_ids: ["chunk-a", "chunk-b"] }),
    ]);

    const btn = wrapper.find(".timeline__evidence-ids");
    await btn.trigger("keydown", { key: "Enter" });

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText).toHaveBeenCalledWith("chunk-a, chunk-b");
  });

  it("evidence copy button copies IDs on Space key", async () => {
    const writeText = _stubClipboard();
    const wrapper = await mountTimeline([
      _span({ evidence_ids: ["single-chunk"] }),
    ]);

    const btn = wrapper.find(".timeline__evidence-ids");
    await btn.trigger("keydown", { key: " " });

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText).toHaveBeenCalledWith("single-chunk");
  });

  it("empty evidence shows non-interactive placeholder only", async () => {
    const wrapper = await mountTimeline([_span()]);
    const btn = wrapper.find(".timeline__evidence-ids");
    expect(btn.exists()).toBe(false);
    expect(wrapper.text()).toContain("无引用");
  });

  it("evidence button has aria-label", async () => {
    const wrapper = await mountTimeline([
      _span({ evidence_ids: ["r1"] }),
    ]);
    const btn = wrapper.find(".timeline__evidence-ids");
    expect(btn.attributes("aria-label")).toContain("复制证据 ID");
  });
});
