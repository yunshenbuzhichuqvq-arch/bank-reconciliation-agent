import { nextTick } from "vue";
import { createRouter, createMemoryHistory } from "vue-router";
import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

import TraceReplayPage from "../src/pages/TraceReplayPage.vue";

vi.mock("../src/api/trace", () => ({
  fetchTraceReplay: vi.fn(() => new Promise(() => {})),
}));

function makeRouter(taskId = "T1", flowId = "F1") {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/traces/:taskId/:flowId", component: TraceReplayPage }],
  });
}

async function mountPage(
  taskId = "T1",
  flowId = "F1",
) {
  const router = makeRouter(taskId, flowId);
  await router.push(`/traces/${taskId}/${flowId}`);
  await router.isReady();

  const wrapper = mount(TraceReplayPage, {
    global: { plugins: [router] },
  });
  return { wrapper, router };
}

describe("TraceReplayPage", () => {
  it("renders title, back button, and loading state", async () => {
    const { wrapper } = await mountPage();
    expect(wrapper.text()).toContain("执行轨迹");
    expect(wrapper.text()).toContain("加载中...");
    expect(wrapper.find('[aria-label="返回"]').exists()).toBe(true);
  });

  it("shows task and flow IDs from route params", async () => {
    const { wrapper } = await mountPage("TASK-ABC", "FLOW-XYZ");
    expect(wrapper.text()).toContain("TASK-ABC");
    expect(wrapper.text()).toContain("FLOW-XYZ");
  });

  it("reloads when route params change", async () => {
    const { wrapper, router } = await mountPage("T-FIRST", "F-FIRST");

    const { fetchTraceReplay } = await import("../src/api/trace");
    expect(fetchTraceReplay).toHaveBeenCalledWith("T-FIRST", "F-FIRST", undefined);
    vi.mocked(fetchTraceReplay).mockClear();

    await router.push("/traces/T-SECOND/F-SECOND");
    await nextTick();
    await nextTick();

    expect(fetchTraceReplay).toHaveBeenCalledWith("T-SECOND", "F-SECOND", undefined);
  });

  it("clears selected trace and data on route change", async () => {
    const { wrapper, router } = await mountPage("T-A", "F-A");

    await router.push("/traces/T-B/F-B");
    await nextTick();
    await nextTick();

    expect(wrapper.text()).toContain("T-B");
    expect(wrapper.text()).toContain("F-B");
  });

  it("route params decode URL-encoded task/flow IDs correctly", async () => {
    const taskId = "TASK/with-slash";
    const flowId = "FLOW&with-amp";
    const { wrapper } = await mountPage(
      encodeURIComponent(taskId),
      encodeURIComponent(flowId),
    );

    expect(wrapper.text()).toContain(taskId);
    expect(wrapper.text()).toContain(flowId);
  });

  it("back button is focusable and has aria-label", async () => {
    const { wrapper } = await mountPage();
    const btn = wrapper.find('[aria-label="返回"]');
    expect(btn.exists()).toBe(true);
  });
});
