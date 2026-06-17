import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "../src/pages/DashboardPage.vue";

const apiState = vi.hoisted(() => ({
  getTaskStatus: vi.fn(async () => ({
    task_id: "TASK-1",
    status: "UPLOADED",
    auto_fixed_rows: 1,
    pending_ai_rows: 2,
    ai_processed_rows: 3,
    pending_human_rows: 4,
    unresolved_rows: 5,
  })),
  getTaskExceptions: vi.fn(async () => ({ task_id: "TASK-1", total: 0, items: [] })),
  startLiveReconciliation: vi.fn(async () => ({ task_id: "TASK-1", status: "AI_RUNNING" })),
}));

vi.mock("../src/api/reconcile", () => apiState);
vi.mock("../src/composables/useTaskEventStream", () => ({
  useTaskEventStream: () => ({
    events: { value: [] },
    progress: { value: null },
    status: { value: "idle" },
    error: { value: null },
    start: vi.fn(),
    abort: vi.fn(),
  }),
}));

async function mountDashboard() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/tasks/:taskId", component: DashboardPage }],
  });
  router.push("/tasks/TASK-1");
  await router.isReady();

  const wrapper = mount(DashboardPage, {
    global: {
      plugins: [router],
    },
  });
  await flushPromises();
  return wrapper;
}

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps manual refresh and wires audit start to the live task stream", async () => {
    const wrapper = await mountDashboard();

    expect(apiState.getTaskStatus).toHaveBeenCalledWith("TASK-1");
    expect(apiState.getTaskExceptions).toHaveBeenCalledWith("TASK-1");

    apiState.getTaskStatus.mockClear();
    apiState.getTaskExceptions.mockClear();

    const refreshButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("刷新"));
    expect(refreshButton).toBeDefined();
    await refreshButton!.trigger("click");
    await flushPromises();

    expect(apiState.getTaskStatus).toHaveBeenCalledWith("TASK-1");
    expect(apiState.getTaskExceptions).toHaveBeenCalledWith("TASK-1");

    apiState.getTaskStatus.mockClear();
    apiState.getTaskExceptions.mockClear();

    const startButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("启动 AI 审计"));
    expect(startButton).toBeDefined();
    await startButton!.trigger("click");
    await flushPromises();

    expect(apiState.startLiveReconciliation).toHaveBeenCalledWith("TASK-1");
    expect(apiState.getTaskStatus).toHaveBeenCalledWith("TASK-1");
    expect(apiState.getTaskExceptions).toHaveBeenCalledWith("TASK-1");
  });
});
