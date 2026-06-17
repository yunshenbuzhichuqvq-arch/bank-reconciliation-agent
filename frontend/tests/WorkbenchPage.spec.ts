import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";

import WorkbenchPage from "../src/pages/WorkbenchPage.vue";
import workbenchSource from "../src/pages/WorkbenchPage.vue?raw";
import { router } from "../src/router";
import type { AgentStreamEvent } from "../src/types/api";

const streamState = vi.hoisted(() => ({
  events: { value: [] as AgentStreamEvent[] },
  status: { value: "idle" as "idle" | "streaming" | "done" | "error" },
  result: { value: null as AgentStreamEvent["payload"] | null },
  error: { value: null as string | null },
  start: vi.fn(),
  abort: vi.fn(),
}));

vi.mock("../src/composables/useReconcileStream", () => ({
  useReconcileStream: () => streamState,
}));

function streamEvent(event: AgentStreamEvent): AgentStreamEvent {
  return event;
}

async function renderWorkbench() {
  const app = createSSRApp(WorkbenchPage);
  return renderToString(app);
}

describe("WorkbenchPage", () => {
  it("renders stream events in order and task_done summary counts", async () => {
    streamState.status.value = "done";
    streamState.result.value = {
      status: "COMPLETED",
      total_bank_rows: 3,
      total_clear_rows: 3,
      auto_fixed_rows: 2,
      pending_ai_rows: 0,
      pending_human_rows: 1,
    };
    streamState.events.value = [
      streamEvent({
        schema_version: "1.0",
        event_type: "task_started",
        seq: 0,
        task_id: "PENDING",
        flow_id: null,
        ts: "2026-06-15T00:00:00Z",
        payload: { scenario_type: "BANK_ENTERPRISE" },
      }),
      streamEvent({
        schema_version: "1.0",
        event_type: "rag_retrieved",
        seq: 1,
        task_id: "PENDING",
        flow_id: "FLOW-1",
        ts: "2026-06-15T00:00:01Z",
        payload: { agent_name: "AuditAgent", chunk_ids: ["R-1"], best_score: 0.87, query: "金额差异" },
      }),
      streamEvent({
        schema_version: "1.0",
        event_type: "task_done",
        seq: 2,
        task_id: "TASK-1",
        flow_id: null,
        ts: "2026-06-15T00:00:02Z",
        payload: streamState.result.value,
      }),
    ];

    const html = await renderWorkbench();

    expect(html.indexOf("任务启动")).toBeLessThan(html.indexOf("RAG 召回"));
    expect(html.indexOf("RAG 召回")).toBeLessThan(html.indexOf("任务完成"));
    expect(html).toContain("银行端流水");
    expect(html).toContain(">3<");
    expect(html).toContain("自动修复");
    expect(html).toContain(">2<");
    expect(html).toContain("待人工复核");
    expect(html).toContain(">1<");
  });

  it("registers the workbench route", () => {
    expect(router.getRoutes().some((route) => route.path === "/workbench")).toBe(true);
  });

  it("renders both scenarios and passes the selected clearing scenario to the stream", async () => {
    const html = await renderWorkbench();
    expect(html).toContain("银企对账");
    expect(html).toContain("银行清算对账");

    expect(workbenchSource).toContain("ref<ScenarioType>(\"BANK_ENTERPRISE\")");
    expect(workbenchSource).toContain("v-for=\"[value, meta] in scenarioEntries\"");
    expect(workbenchSource).toContain("scenarioType: scenario.value");
  });
});
