import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import ReviewCard from "../src/components/review/ReviewCard.vue";
import type { PendingReviewItem } from "../src/types/api";

const _bilateral: PendingReviewItem = {
  queue_id: 1,
  error_type: "AMOUNT_MISMATCH",
  exception_branch: "BE-R002",
  risk_level: "MEDIUM",
  ai_suggestion: "PENDING_HUMAN",
  ai_confidence: 0.85,
  ai_reason: "金额不一致",
  rag_sources: [{ source: "rule-001", score: 0.95 }],
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

const _singleSided: PendingReviewItem = {
  queue_id: 2,
  error_type: "BANK_UNARRIVED",
  exception_branch: "BE-R005",
  risk_level: "MEDIUM",
  ai_suggestion: "PENDING_HUMAN",
  ai_confidence: 0.7,
  ai_reason: "银行未到账",
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

const _approvedMatch: PendingReviewItem = {
  ..._bilateral,
  queue_id: 3,
  ai_suggestion: "APPROVED_MATCH",
};

const _forceHold: PendingReviewItem = {
  ..._bilateral,
  queue_id: 4,
  ai_suggestion: "FORCE_HOLD",
};

function mountCard(item: PendingReviewItem) {
  return mount(ReviewCard, {
    props: { item },
    global: {
      stubs: {
        BaseButton: { template: "<button><slot /></button>" },
        BaseCard: { template: "<div><slot name='header' /><slot /><slot name='footer' /></div>" },
        RiskBadge: { template: "<span />" },
      },
    },
  });
}

describe("ReviewCard", () => {
  it("shows flow_id as primary identifier", () => {
    const wrapper = mountCard(_bilateral);
    expect(wrapper.text()).toContain("FLOW-001");
  });

  it("shows task_id and queue_id as secondary identifiers", () => {
    const wrapper = mountCard(_bilateral);
    expect(wrapper.text()).toContain("TASK-1");
    expect(wrapper.text()).toContain("1");
  });

  it("renders bank and clear serial numbers", () => {
    const wrapper = mountCard(_bilateral);
    expect(wrapper.text()).toContain("B202606010003");
    expect(wrapper.text()).toContain("C202606010003");
  });

  it("renders bank_amount, clear_amount and discrepancy_amount", () => {
    const wrapper = mountCard(_bilateral);
    expect(wrapper.text()).toContain("1000.00");
    expect(wrapper.text()).toContain("980.00");
    expect(wrapper.text()).toContain("20.00");
  });

  it("does not render 0.00 for null amount fields on single-sided item", () => {
    const wrapper = mountCard(_singleSided);
    const text = wrapper.text();
    const matchNull = (text.match(/无对应流水/g) || []).length;
    expect(matchNull).toBeGreaterThanOrEqual(2);
    expect(_singleSided.bank_amount).toBeNull();
  });

  it("shows 待人工复核 for ai_suggestion PENDING_HUMAN", () => {
    const wrapper = mountCard(_bilateral);
    expect(wrapper.text()).toContain("待人工复核");
    expect(wrapper.text()).not.toContain("PENDING_HUMAN");
  });

  it("shows 待人工复核 for ai_suggestion APPROVED_MATCH instead of raw token", () => {
    const wrapper = mountCard(_approvedMatch);
    expect(wrapper.text()).toContain("待人工复核");
    expect(wrapper.text()).not.toContain("APPROVED_MATCH");
  });

  it("shows 待人工复核 for ai_suggestion FORCE_HOLD instead of raw token", () => {
    const wrapper = mountCard(_forceHold);
    expect(wrapper.text()).toContain("待人工复核");
    expect(wrapper.text()).not.toContain("FORCE_HOLD");
  });

  it("does not render historical reference placeholder", () => {
    const wrapper = mountCard(_bilateral);
    expect(wrapper.text()).not.toContain("相似案例");
    expect(wrapper.text()).not.toContain("历史参考");
    expect(wrapper.text()).not.toContain("历史通过率");
  });

  it("emits FORCE_HOLD action", async () => {
    const wrapper = mountCard(_bilateral);
    const buttons = wrapper.findAll("button");
    const holdBtn = buttons.find((b) => b.text() === "强制挂账");
    expect(holdBtn).toBeTruthy();
    await holdBtn!.trigger("click");
    const emitted = wrapper.emitted("action");
    expect(emitted).toBeTruthy();
    expect(emitted![0]).toEqual([_bilateral, "FORCE_HOLD"]);
  });

  it("emits APPROVED_MATCH action", async () => {
    const wrapper = mountCard(_bilateral);
    const buttons = wrapper.findAll("button");
    const approveBtn = buttons.find((b) => b.text() === "确认平账");
    expect(approveBtn).toBeTruthy();
    await approveBtn!.trigger("click");
    const emitted = wrapper.emitted("action");
    expect(emitted).toBeTruthy();
    const match = emitted!.find((e) => e[1] === "APPROVED_MATCH");
    expect(match).toBeTruthy();
    expect(match![0]).toEqual(_bilateral);
  });
});
