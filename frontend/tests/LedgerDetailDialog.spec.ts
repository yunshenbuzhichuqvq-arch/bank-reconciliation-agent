import { nextTick, ref } from "vue";
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

  it("goToTrace pushes correct encoded route and closes dialog", async () => {
    const { wrapper, router } = await mountDialog();

    const pushSpy = vi.spyOn(router, "push");

    const btn = wrapper.find(".btn-trace");
    await btn.trigger("click");
    await nextTick();

    expect(pushSpy).toHaveBeenCalledWith(
      `/traces/${encodeURIComponent("TASK-1")}/${encodeURIComponent("FLOW-1")}`,
    );

    const emitted = wrapper.emitted("update:modelValue");
    expect(emitted).toBeTruthy();
    expect(emitted![0]).toEqual([false]);
  });

  it("encodes reserved characters in task/flow IDs", async () => {
    const { wrapper, router } = await mountDialog({
      task_id: "TASK#1/2?x=y",
      flow_id: "FLOW&3=4",
    });

    const pushSpy = vi.spyOn(router, "push");
    const btn = wrapper.find(".btn-trace");
    await btn.trigger("click");

    const taskEncoded = encodeURIComponent("TASK#1/2?x=y");
    const flowEncoded = encodeURIComponent("FLOW&3=4");
    expect(pushSpy).toHaveBeenCalledWith(
      `/traces/${taskEncoded}/${flowEncoded}`,
    );
  });
});
