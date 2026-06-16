import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { readFileSync } from "node:fs";
import { createRouter, createMemoryHistory } from "vue-router";
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

async function renderDashboard() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/tasks/:taskId", component: DashboardPage }],
  });
  router.push("/tasks/TASK-1");
  await router.isReady();

  const app = createSSRApp(DashboardPage);
  app.use(router);
  return renderToString(app);
}

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps manual refresh and wires audit start to the live task stream", async () => {
    const html = await renderDashboard();
    const source = readFileSync(new URL("../src/pages/DashboardPage.vue", import.meta.url), "utf8");

    expect(apiState.getTaskStatus).toHaveBeenCalledWith("TASK-1");
    expect(apiState.getTaskExceptions).toHaveBeenCalledWith("TASK-1");
    expect(source).toContain("startLiveReconciliation");
    expect(source).toContain("useTaskEventStream");
    expect(source).toContain("taskStream.progress");
    expect(source).not.toContain("startReconciliation");
    expect(html).toContain("刷新");
    expect(html).toContain("自动修复");
    expect(html).toContain(">1<");
    expect(html).toContain("AI 已处理");
    expect(html).toContain(">3<");
    expect(html).toContain("待人工复核");
    expect(html).toContain(">4<");
  });
});
