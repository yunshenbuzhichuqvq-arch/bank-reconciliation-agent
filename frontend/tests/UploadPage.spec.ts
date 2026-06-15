import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { createRouter, createMemoryHistory } from "vue-router";
import { describe, expect, it, vi } from "vitest";

import UploadPage from "../src/pages/UploadPage.vue";
import { SCENARIO_META } from "../src/constants/enums";

vi.mock("../src/api/reconcile", () => ({
  uploadReconciliation: vi.fn(),
}));

async function renderUploadPage() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/upload", component: UploadPage }],
  });
  router.push("/upload");
  await router.isReady();

  const app = createSSRApp(UploadPage);
  app.use(router);
  return renderToString(app);
}

describe("UploadPage", () => {
  it("renders both scenario choices and their field templates", async () => {
    const html = await renderUploadPage();

    expect(html).toContain("银企对账");
    expect(html).toContain("银行清算对账");
    expect(html).toContain("银行账号、交易日期、借贷方向、发生额、对方户名");
    expect(SCENARIO_META.BANK_CLEARING.clearTemplate).toBe(
      "清算渠道、清算日期、订单号、清算金额、手续费",
    );
  });
});
