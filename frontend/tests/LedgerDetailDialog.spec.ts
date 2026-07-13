import { createRouter, createMemoryHistory } from "vue-router";
import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

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

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/traces/:taskId/:flowId", component: { template: "<div/>" } },
      { path: "/ledger", component: { template: "<div/>" } },
    ],
  });
}

async function mountDialog(overrides: Partial<LedgerRow> = {}) {
  const router = makeRouter();
  await router.push("/ledger");
  await router.isReady();

  const wrapper = mount(LedgerDetailDialog, {
    global: {
      plugins: [router],
      stubs: {
        ElDialog: {
          template: "<div><slot /></div>",
          inheritAttrs: false,
        },
        StatusBadge: { template: "<span />" },
      },
    },
    props: { modelValue: true, row: { ..._row, ...overrides } },
  });
  return { wrapper, router };
}

describe("LedgerDetailDialog", () => {
  it("renders task and flow identifiers", async () => {
    const { wrapper } = await mountDialog();
    expect(wrapper.text()).toContain("TASK-1");
    expect(wrapper.text()).toContain("FLOW-1");
  });

  it("renders trace replay button", async () => {
    const { wrapper } = await mountDialog();
    const btn = wrapper.find(".btn-trace");
    expect(btn.exists()).toBe(true);
    expect(btn.text()).toContain("查看执行轨迹");
  });

  it("navigates to correct route and closes dialog", async () => {
    const { wrapper, router } = await mountDialog();

    const pushSpy = vi.spyOn(router, "push");

    const btn = wrapper.find(".btn-trace");
    await btn.trigger("click");

    expect(pushSpy).toHaveBeenCalledWith(
      `/traces/${encodeURIComponent("TASK-1")}/${encodeURIComponent("FLOW-1")}`,
    );

    const emitted = wrapper.emitted("update:modelValue");
    expect(emitted).toBeTruthy();
    expect(emitted![0]).toEqual([false]);
  });

  it("encodes reserved characters and preserves decoded route params", async () => {
    const { wrapper, router } = await mountDialog({
      task_id: "T/A#S?K&1",
      flow_id: "F=L:O;W",
    });

    const pushSpy = vi.spyOn(router, "push");

    const btn = wrapper.find(".btn-trace");
    await btn.trigger("click");

    const taskEncoded = encodeURIComponent("T/A#S?K&1");
    const flowEncoded = encodeURIComponent("F=L:O;W");
    expect(pushSpy).toHaveBeenCalledWith(
      `/traces/${taskEncoded}/${flowEncoded}`,
    );
    // Each reserved char encoded exactly once; no double-wrap.
    expect(taskEncoded).toContain("%2F");
    expect(taskEncoded).toContain("%23");
    expect(taskEncoded).toContain("%3F");
    expect(taskEncoded).toContain("%26");
    // One / in "T/A#S?K&1".
    expect(taskEncoded.match(/%2F/g)?.length).toBe(1);
    expect(taskEncoded.match(/%26/g)?.length).toBe(1);
  });

  it("renders bank and clear amounts in detail", async () => {
    const { wrapper } = await mountDialog();
    expect(wrapper.text()).toContain("100.00");
    expect(wrapper.text()).toContain("99.00");
    expect(wrapper.text()).toContain("1.00");
  });

  it("renders AI audit opinion", async () => {
    const { wrapper } = await mountDialog();
    expect(wrapper.text()).toContain("金额不一致");
  });

  it("renders error type and branch", async () => {
    const { wrapper } = await mountDialog();
    expect(wrapper.text()).toContain("BE-R002");
  });
});
