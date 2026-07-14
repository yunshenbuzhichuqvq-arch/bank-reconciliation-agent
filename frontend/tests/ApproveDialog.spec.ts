import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import ApproveDialog from "../src/components/review/ApproveDialog.vue";
import type { PendingReviewItem, ReviewAction } from "../src/types/api";

const _item: PendingReviewItem = {
  queue_id: 1,
  error_type: "AMOUNT_MISMATCH",
  exception_branch: "BE-R002",
  risk_level: "MEDIUM",
  ai_suggestion: "PENDING_HUMAN",
  ai_confidence: 0.85,
  ai_reason: "金额不一致",
  rag_sources: [],
  similar_historical_cases: 0,
  historical_approve_rate: "0%",
  task_id: "TASK-1",
  flow_id: "FLOW-001",
  bank_serial_no: "B202606010003",
  clearing_serial_no: "C202606010003",
  bank_amount: "1000.00",
  clear_amount: "980.00",
  discrepancy_amount: "20.00",
};

const _nullItem: PendingReviewItem = {
  queue_id: 2,
  error_type: "BANK_UNARRIVED",
  exception_branch: "BE-R005",
  risk_level: "MEDIUM",
  ai_suggestion: "PENDING_HUMAN",
  ai_confidence: null,
  ai_reason: null,
  rag_sources: [],
  similar_historical_cases: 0,
  historical_approve_rate: "0%",
  task_id: "TASK-1",
  flow_id: "FLOW-005",
  bank_serial_no: null,
  clearing_serial_no: "C202606010005",
  bank_amount: null,
  clear_amount: "760.00",
  discrepancy_amount: "760.00",
};

function mountDialog(props: Partial<{
  modelValue: boolean;
  item: PendingReviewItem | null;
  action: ReviewAction | null;
  loading: boolean;
  initialHandler: string;
}> = {}) {
  return mount(ApproveDialog, {
    props: {
      modelValue: true,
      item: _item,
      action: "APPROVED_MATCH",
      loading: false,
      initialHandler: "reviewer_a",
      ...props,
    },
    global: {
      stubs: {
        ElDialog: {
          template: "<div><slot /><slot name='footer' /></div>",
          inheritAttrs: false,
        },
        ElInput: {
          template: "<input :value='modelValue' @input='$emit(\"update:modelValue\", \"\")' />",
          props: ["modelValue", "placeholder", "type", "rows"],
          inheritAttrs: false,
        },
        BaseButton: { template: "<button><slot /></button>" },
      },
    },
  });
}

describe("ApproveDialog", () => {
  it("shows flow_id in summary instead of only queue_id", () => {
    const wrapper = mountDialog();
    expect(wrapper.text()).toContain("FLOW-001");
  });

  it("shows bank and clear amounts with discrepancy in context", () => {
    const wrapper = mountDialog();
    expect(wrapper.text()).toContain("1000.00");
    expect(wrapper.text()).toContain("980.00");
    expect(wrapper.text()).toContain("20.00");
  });

  it("shows 无对应流水 for null amount side", () => {
    const wrapper = mountDialog({ item: _nullItem });
    expect(wrapper.text()).toContain("无对应流水");
  });

  it("includes handler_username in confirm payload", async () => {
    const wrapper = mountDialog({ initialHandler: "handler_x" });

    const buttons = wrapper.findAll("button");
    const submitBtn = buttons.find((b) => b.text() === "确认提交");
    expect(submitBtn).toBeTruthy();
    await submitBtn!.trigger("click");

    const emitted = wrapper.emitted("confirm");
    expect(emitted).toBeTruthy();
    expect(emitted![0][0]).toMatchObject({ handler_username: "handler_x" });
  });

  it("includes remark when provided", async () => {
    const wrapper = mountDialog({ initialHandler: "reviewer" });

    const buttons = wrapper.findAll("button");
    const submitBtn = buttons.find((b) => b.text() === "确认提交");
    expect(submitBtn).toBeTruthy();
    await submitBtn!.trigger("click");

    const emitted = wrapper.emitted("confirm");
    expect(emitted).toBeTruthy();
  });

  it("closes on cancel", async () => {
    const wrapper = mountDialog();

    const buttons = wrapper.findAll("button");
    const cancelBtn = buttons.find((b) => b.text() === "取消");
    expect(cancelBtn).toBeTruthy();
    await cancelBtn!.trigger("click");

    const emitted = wrapper.emitted("update:modelValue");
    expect(emitted).toBeTruthy();
    expect(emitted![0]).toEqual([false]);
  });

  it("shows actionLabel for APPROVED_MATCH", () => {
    const wrapper = mountDialog({ action: "APPROVED_MATCH" });
    expect(wrapper.text()).toContain("确认平账");
  });

  it("shows actionLabel for FORCE_HOLD", () => {
    const wrapper = mountDialog({ action: "FORCE_HOLD" });
    expect(wrapper.text()).toContain("强制挂账");
  });
});
