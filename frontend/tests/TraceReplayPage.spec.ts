import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { createRouter, createMemoryHistory } from "vue-router";
import { describe, expect, it, vi } from "vitest";

import TraceReplayPage from "../src/pages/TraceReplayPage.vue";

vi.mock("../src/api/trace", () => ({
  fetchTraceReplay: vi.fn(() => new Promise(() => {})),
}));

async function renderPage() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/traces/:taskId/:flowId", component: TraceReplayPage }],
  });
  router.push("/traces/T1/F1");
  await router.isReady();

  const app = createSSRApp(TraceReplayPage);
  app.use(router);
  return renderToString(app);
}

describe("TraceReplayPage", () => {
  it("renders initial loading state with title and back button", async () => {
    const html = await renderPage();
    expect(html).toContain("执行轨迹");
    expect(html).toContain("T1 / F1");
    expect(html).toContain("加载中...");
    expect(html).toContain('aria-label="返回"');
  });
});
