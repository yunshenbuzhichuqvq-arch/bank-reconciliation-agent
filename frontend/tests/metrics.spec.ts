import { afterEach, describe, expect, it, vi } from "vitest";

import { getDashboardMetrics } from "../src/api/metrics";

const apiGet = vi.hoisted(() =>
  vi.fn(async (_url: string) => ({
    online: {
      auto_fix_rate: 0.625,
      pending_human_count: 3,
      hung_count: 1,
      exception_dist: { AMOUNT_MISMATCH: 2, BANK_UNARRIVED: 1 },
      fallback_dist: { "L1->L2": 2 },
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
  })),
);

vi.mock("../src/api/client", () => ({
  apiGet,
}));

describe("metrics api", () => {
  afterEach(() => {
    apiGet.mockClear();
  });

  it("loads dashboard metrics from the backend metrics endpoint", async () => {
    const result = await getDashboardMetrics();

    expect(apiGet).toHaveBeenCalledWith("/metrics/dashboard");
    expect(result.online.auto_fix_rate).toBe(0.625);
    expect(result.offline).toMatchObject({ evaluated_at: "2026-06-16T11:00:00Z" });
    expect(result.unavailable.latency).toBe("no_data_source");
  });
});
