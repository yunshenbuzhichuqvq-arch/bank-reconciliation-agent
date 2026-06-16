import { renderToString } from "@vue/server-renderer";
import ElementPlus, { ID_INJECTION_KEY, ZINDEX_INJECTION_KEY } from "element-plus";
import { createSSRApp } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "../src/pages/DashboardPage.vue";
import LedgerPage from "../src/pages/LedgerPage.vue";
import ReviewPage from "../src/pages/ReviewPage.vue";
import UploadPage from "../src/pages/UploadPage.vue";
import WorkbenchPage from "../src/pages/WorkbenchPage.vue";
import { router } from "../src/router";

const reconcileApi = vi.hoisted(() => ({
  getTaskStatus: vi.fn(async () => ({
    task_id: "TASK-1",
    status: "UPLOADED",
    auto_fixed_rows: 1,
    pending_ai_rows: 0,
    ai_processed_rows: 1,
    pending_human_rows: 1,
    unresolved_rows: 1,
  })),
  getTaskExceptions: vi.fn(async () => ({ task_id: "TASK-1", total: 0, items: [] })),
  startLiveReconciliation: vi.fn(async () => ({ task_id: "TASK-1", status: "AI_RUNNING" })),
  uploadReconciliation: vi.fn(),
}));

const ledgerApi = vi.hoisted(() => ({
  listLedger: vi.fn(async () => ({ items: [], total: 0, page: 1, page_size: 20 })),
}));

const reviewApi = vi.hoisted(() => ({
  listPending: vi.fn(async () => ({ items: [], total: 0, page: 1, page_size: 10 })),
  approveReview: vi.fn(),
}));

const workbenchStream = vi.hoisted(() => ({
  events: { value: [] },
  status: { value: "idle" },
  result: { value: null },
  error: { value: null },
  start: vi.fn(),
  abort: vi.fn(),
}));

vi.mock("../src/api/reconcile", () => reconcileApi);
vi.mock("../src/api/ledger", () => ledgerApi);
vi.mock("../src/api/review", () => reviewApi);
vi.mock("../src/composables/useReconcileStream", () => ({
  useReconcileStream: () => workbenchStream,
}));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal<typeof import("element-plus")>();
  return {
    ...actual,
    ElMessage: { success: vi.fn(), error: vi.fn() },
  };
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("localStorage", {
    getItem: vi.fn(() => null),
    setItem: vi.fn(),
  });
});

async function renderPage(path: string, component: object) {
  const testRouter = createRouter({
    history: createMemoryHistory(),
    routes: [{ path, component }],
  });
  testRouter.push(path.includes(":taskId") ? "/tasks/TASK-1" : path);
  await testRouter.isReady();

  const app = createSSRApp(component);
  app.use(testRouter);
  app.use(ElementPlus);
  app.provide(ID_INJECTION_KEY, { prefix: 1024, current: 0 });
  app.provide(ZINDEX_INJECTION_KEY, { current: 0 });
  return renderToString(app);
}

describe("V1-3.8 page regression smoke", () => {
  it("keeps the five existing pages renderable", async () => {
    const [uploadHtml, workbenchHtml, ledgerHtml, reviewHtml, dashboardHtml] = await Promise.all([
      renderPage("/upload", UploadPage),
      renderPage("/workbench", WorkbenchPage),
      renderPage("/ledger", LedgerPage),
      renderPage("/review", ReviewPage),
      renderPage("/tasks/:taskId", DashboardPage),
    ]);

    expect(uploadHtml).toContain("上传对账单");
    expect(workbenchHtml).toContain("Agent 流式工作台");
    expect(ledgerHtml).toContain("差错台账");
    expect(reviewHtml).toContain("人工复核");
    expect(dashboardHtml).toContain("任务看板");
    expect(reconcileApi.getTaskStatus).toHaveBeenCalledWith("TASK-1");
  });

  it("keeps existing routes reachable after adding metrics", () => {
    const paths = router.getRoutes().map((route) => route.path);

    expect(paths).toEqual(
      expect.arrayContaining(["/upload", "/workbench", "/ledger", "/review", "/tasks/:taskId"]),
    );
  });
});
