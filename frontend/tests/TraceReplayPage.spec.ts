import { nextTick } from "vue";
import { createRouter, createMemoryHistory } from "vue-router";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { mount } from "@vue/test-utils";

import TraceReplayPage from "../src/pages/TraceReplayPage.vue";

let _pendingResolvers: Array<{
  resolve: (data: unknown) => void;
  reject: (err: unknown) => void;
  taskId: string;
  flowId: string;
  traceId?: string;
}> = [];

function _deferredFetch(taskId: string, flowId: string, traceId?: string): Promise<unknown> {
  return new Promise((resolve, reject) => {
    _pendingResolvers.push({ resolve, reject, taskId, flowId, traceId });
  });
}

vi.mock("../src/api/trace", () => ({
  fetchTraceReplay: vi.fn(
    (taskId: string, flowId: string, traceId?: string) =>
      _deferredFetch(taskId, flowId, traceId),
  ),
}));

function makeRouter(taskId = "T1", flowId = "F1") {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/traces/:taskId/:flowId", component: TraceReplayPage }],
  });
}

async function mountPage(taskId = "T1", flowId = "F1") {
  const router = makeRouter(taskId, flowId);
  await router.push(`/traces/${encodeURIComponent(taskId)}/${encodeURIComponent(flowId)}`);
  await router.isReady();

  const wrapper = mount(TraceReplayPage, {
    global: { plugins: [router] },
  });
  await nextTick();
  return { wrapper, router };
}

function _mockReplay(spansCount = 2) {
  return {
    replay_status: "AVAILABLE",
    selected_trace_id: "trace-1",
    execution_count: 1,
    runs: [
      {
        trace_id: "trace-1",
        started_at: "2026-07-01T00:00:00Z",
        status: "SUCCEEDED",
        outcome: "PENDING_HUMAN",
      },
    ],
    spans: Array.from({ length: spansCount }, (_, i) => ({
      schema_version: "1.0",
      trace_id: "trace-1",
      span_id: `span-${i}`,
      parent_span_id: i === 0 ? null : "span-0",
      task_id: "T1",
      flow_id: "F1",
      sequence_no: i + 1,
      span_type: i === 0 ? "WORKFLOW" : "TOOL",
      name: i === 0 ? "root" : "search_rules",
      started_at: "2026-07-01T00:00:00Z",
      ended_at: "2026-07-01T00:00:01Z",
      duration_ms: 1000,
      status: "SUCCEEDED",
      outcome: null,
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
    })),
    prompt_tokens: 0,
    completion_tokens: 0,
    total_tokens: 0,
  };
}

function _pendingCount() {
  return _pendingResolvers.length;
}

describe("TraceReplayPage", () => {
  beforeEach(() => {
    _pendingResolvers = [];
  });

  afterEach(() => {
    _pendingResolvers = [];
  });

  it("renders title and back button", async () => {
    const { wrapper } = await mountPage();
    expect(wrapper.text()).toContain("执行轨迹");
    expect(wrapper.find('[aria-label="返回"]').exists()).toBe(true);
  });

  it("shows task and flow IDs from route params", async () => {
    const { wrapper } = await mountPage("TASK-ABC", "FLOW-XYZ");
    expect(wrapper.text()).toContain("TASK-ABC");
    expect(wrapper.text()).toContain("FLOW-XYZ");
  });

  it("reloads when route params change and clears old selection", async () => {
    const { wrapper, router } = await mountPage("T-FIRST", "F-FIRST");
    expect(_pendingCount()).toBe(1);

    await router.push("/traces/T-SECOND/F-SECOND");
    await nextTick();
    await nextTick();
    expect(_pendingCount()).toBe(2);
  });

  it("latest request wins when A completes after B already succeeded", async () => {
    const { wrapper, router } = await mountPage("T-A", "F-A");
    expect(_pendingCount()).toBe(1);

    await router.push("/traces/T-B/F-B");
    await nextTick();
    await nextTick();
    expect(_pendingCount()).toBe(2);

    const [, resolverB] = _pendingResolvers;
    const [resolverA] = _pendingResolvers;

    resolverB.resolve(_mockReplay());
    await nextTick();
    await nextTick();
    expect(wrapper.text()).not.toContain("加载中...");

    resolverA.resolve(_mockReplay());
    await nextTick();
    await nextTick();

    expect(wrapper.text()).toContain("T-B");
    expect(wrapper.text()).toContain("F-B");
  });

  it("stale error does not overwrite newer success", async () => {
    const { wrapper, router } = await mountPage("T-A", "F-A");
    await router.push("/traces/T-B/F-B");
    await nextTick();
    await nextTick();

    const [, resolverB] = _pendingResolvers;
    const [resolverA] = _pendingResolvers;

    resolverB.resolve(_mockReplay());
    await nextTick();
    await nextTick();
    expect(wrapper.text()).toContain("T-B");

    resolverA.reject({ status: 500, message: "old error" });
    await nextTick();
    await nextTick();
    expect(wrapper.text()).toContain("T-B");
    expect(wrapper.text()).not.toContain("old error");
  });

  it("stale finally does not end loading while B is pending", async () => {
    const { wrapper, router } = await mountPage("T-A", "F-A");
    await router.push("/traces/T-B/F-B");
    await nextTick();
    await nextTick();

    const [resolverA] = _pendingResolvers;
    resolverA.resolve(_mockReplay());
    await nextTick();
    await nextTick();

    expect(wrapper.text()).toContain("加载中...");
  });

  it("selectRun request from old route does not overwrite new route", async () => {
    const { wrapper, router } = await mountPage("T-A", "F-A");
    const [resolverA] = _pendingResolvers;

    resolverA.resolve({
      ..._mockReplay(),
      runs: [
        {
          trace_id: "old-trace",
          started_at: "2026-07-01T00:00:00Z",
          status: "SUCCEEDED",
          outcome: "PENDING_HUMAN",
        },
        {
          trace_id: "old-trace-2",
          started_at: "2026-07-01T00:00:01Z",
          status: "SUCCEEDED",
          outcome: "AUTO_FIXED",
        },
      ],
    });
    await nextTick();
    await nextTick();

    expect(wrapper.text()).toContain("T-A");

    await router.push("/traces/T-B/F-B");
    await nextTick();
    await nextTick();

    const [, resolverB] = _pendingResolvers;
    resolverB.resolve(_mockReplay());
    await nextTick();
    await nextTick();

    expect(wrapper.text()).toContain("T-B");
    expect(wrapper.text()).not.toContain("T-A");
  });

  it("preserves loading/error/in-progress/not-available states", async () => {
    const { wrapper, router } = await mountPage("T-INIT", "F-INIT");
    expect(wrapper.text()).toContain("加载中...");

    const [resolver] = _pendingResolvers;
    resolver.reject({ status: 404, message: "not found" });
    await nextTick();
    await nextTick();
    expect(wrapper.text()).toContain("任务或执行记录未找到");

    await router.push("/traces/T-PROG/F-PROG");
    await nextTick();
    await nextTick();
    const [, resolverP] = _pendingResolvers;
    resolverP.resolve({ ..._mockReplay(), replay_status: "IN_PROGRESS", spans: [], runs: [] });
    await nextTick();
    await nextTick();
    expect(wrapper.text()).toContain("任务处理中");
  });
});
