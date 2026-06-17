import { renderToString } from "@vue/server-renderer";
import { createSSRApp, h } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { describe, expect, it, vi } from "vitest";

import AppShell from "../src/components/AppShell.vue";
import MetricsPage from "../src/pages/MetricsPage.vue";
import { router } from "../src/router";

const apiState = vi.hoisted(() => ({
  dashboardMetrics: {
    online: {
      auto_fix_rate: 0.625,
      pending_human_count: 3,
      hung_count: 1,
      exception_dist: { AMOUNT_MISMATCH: 2, BANK_UNARRIVED: 1 },
      fallback_dist: { "L1->L2": 2, "L1->L2->L3->HUMAN": 1 },
      total_tokens: 1200,
      total_cost: "0.3456",
      confidence_dist: { high: 5, medium: 2, low: 1, unknown: 1 },
    },
    offline: {
      rag_recall_at5: 0.75,
      rag_mrr: 0.625,
      schema_conformance_rate: 1,
      evaluated_at: "2026-06-16T11:00:00Z",
    },
    unavailable: {
      latency: "no_data_source",
      agent_accuracy: "no_ground_truth",
    },
  },
  getDashboardMetrics: vi.fn(),
}));

vi.mock("../src/api/metrics", () => ({
  getDashboardMetrics: apiState.getDashboardMetrics,
}));
vi.mock("../src/composables/useTheme", () => ({
  useTheme: () => ({ isDark: { value: false }, toggleTheme: vi.fn() }),
}));

vi.mock("echarts/core", () => ({
  use: vi.fn(),
  init: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() })),
}));
vi.mock("echarts/charts", () => ({
  BarChart: {},
  LineChart: {},
  PieChart: {},
}));
vi.mock("echarts/components", () => ({
  GridComponent: {},
  LegendComponent: {},
  TooltipComponent: {},
}));
vi.mock("echarts/renderers", () => ({
  CanvasRenderer: {},
}));

async function renderMetricsPage() {
  apiState.getDashboardMetrics.mockResolvedValueOnce(apiState.dashboardMetrics);
  const app = createSSRApp(MetricsPage);
  return renderToString(app);
}

describe("MetricsPage", () => {
  it("renders online, offline, and unavailable metrics honestly", async () => {
    const html = await renderMetricsPage();

    expect(apiState.getDashboardMetrics).toHaveBeenCalledOnce();
    expect(html).toContain("量化指标");
    expect(html).toContain("线上聚合");
    expect(html).toContain("62.5%");
    expect(html).toContain("待人工复核");
    expect(html).toContain(">3<");
    expect(html).toContain("离线评测");
    expect(html).toContain("Recall@5");
    expect(html).toContain("2026-06-16T11:00:00Z");
    expect(html).toContain("暂无数据源");
    expect(html).not.toContain("P95");
  });

  it("marks offline metrics as not evaluated when no snapshot exists", async () => {
    apiState.getDashboardMetrics.mockResolvedValueOnce({
      ...apiState.dashboardMetrics,
      offline: { status: "no_snapshot" },
    });
    const app = createSSRApp(MetricsPage);

    const html = await renderToString(app);

    expect(html).toContain("未运行评测");
  });

  it("registers the metrics route and navigation item", async () => {
    const testRouter = createRouter({
      history: createMemoryHistory(),
      routes: router.getRoutes().map((route) => ({ path: route.path, component: MetricsPage })),
    });
    testRouter.push("/metrics");
    await testRouter.isReady();
    const app = createSSRApp(AppShell);
    app.use(testRouter);
    app.component("el-icon", { render: () => h("span") });

    const html = await renderToString(app);

    expect(router.getRoutes().some((route) => route.path === "/metrics")).toBe(true);
    expect(html).toContain("量化指标");
  });
});
