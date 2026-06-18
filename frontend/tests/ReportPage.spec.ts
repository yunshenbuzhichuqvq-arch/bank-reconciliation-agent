import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import ReportPage from "../src/pages/ReportPage.vue";

const apiState = vi.hoisted(() => ({
  getTaskReport: vi.fn(),
}));

vi.mock("../src/api/report", () => ({
  getTaskReport: apiState.getTaskReport,
}));

describe("ReportPage", () => {
  it("generates a report and reveals metrics with the download action", async () => {
    apiState.getTaskReport.mockResolvedValueOnce({
      task_id: "TASK_REPORT",
      generated_at: "2026-06-18T08:00:00+00:00",
      llm_used: true,
      metrics: {
        task_id: "TASK_REPORT",
        user_id: "demo_user",
        recon_date: "2026-06-18T07:00:00",
        source_a_rows: 10,
        source_b_rows: 9,
        auto_fixed_rows: 6,
        auto_fix_rate: 0.6,
        ai_processed_rows: 3,
        pending_human_count: 2,
        review_count: 2,
        hold_count: 1,
        discrepancy_amount_total: "15.75",
        exception_dist: { "BE-R002": 1 },
        agent_decision_dist: { PENDING_HUMAN: 1 },
        fallback_dist: { "L1->L2": 1 },
        total_tokens: 321,
        total_cost: "0.1234",
        offline: { status: "no_snapshot" },
        rag_sources: ["rule-a"],
      },
      narrative: {
        risk_summary: "存在需关注的异常事项。",
        review_advice: "建议核对原始凭证。",
        followup: "建议复核后更新状态。",
        llm_used: true,
      },
      markdown: "# TASK_REPORT 审计报告",
    });
    const wrapper = mount(ReportPage);

    await wrapper.get("input").setValue("TASK_REPORT");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(apiState.getTaskReport).toHaveBeenCalledWith("TASK_REPORT");
    expect(wrapper.text()).toContain("10");
    expect(wrapper.text()).toContain("自动平账率");
    expect(wrapper.text()).toContain("60%");
    expect(wrapper.text()).toContain("存在需关注的异常事项。");
    expect(wrapper.get("[data-testid='download-report']").text()).toContain("下载");
  });
});
