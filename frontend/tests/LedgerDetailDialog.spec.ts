import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it } from "vitest";

import LedgerDetailDialog from "../src/components/ledger/LedgerDetailDialog.vue";
import type { LedgerRow } from "../src/types/api";

const _row: LedgerRow = {
  id: 1,
  task_id: "TASK-1",
  flow_id: "FLOW-1",
  error_type: "AMOUNT_MISMATCH",
  exception_branch: "BE-R002",
  bank_amount: "100.00",
  clear_amount: "99.00",
  discrepancy_amount: "1.00",
  ai_audit_opinion: "金额不一致",
  ai_confidence: "0.8800",
  rag_source: "rule-001",
  handle_status: "PENDING_HUMAN",
};

async function renderDialog(overrides: Partial<LedgerRow> = {}) {
  const app = createSSRApp(LedgerDetailDialog, {
    modelValue: true,
    row: { ..._row, ...overrides },
  });
  return renderToString(app);
}

describe("LedgerDetailDialog", () => {
  it("renders task and flow identifiers used for trace navigation", async () => {
    const html = await renderDialog();
    expect(html).toContain("TASK-1");
    expect(html).toContain("FLOW-1");
  });

  it("renders trace replay action button", async () => {
    const html = await renderDialog();
    expect(html).toContain("查看执行轨迹");
  });

  it("renders bank and clear amounts in tabular format", async () => {
    const html = await renderDialog();
    expect(html).toContain("100.00");
    expect(html).toContain("99.00");
  });
});
