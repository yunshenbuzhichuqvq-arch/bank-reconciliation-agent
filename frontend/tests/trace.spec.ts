import { describe, expect, it, vi, afterEach } from "vitest";

const _requests: Array<{ url: string; params?: Record<string, unknown> }> = [];

vi.mock("../src/api/client", () => ({
  apiGet: vi.fn((url: string, params?: Record<string, unknown>) => {
    _requests.push({ url, params });
    return Promise.resolve({});
  }),
  apiPost: vi.fn(),
  apiUpload: vi.fn(),
}));

import { fetchTraceReplay } from "../src/api/trace";

describe("fetchTraceReplay", () => {
  afterEach(() => {
    _requests.length = 0;
  });

  it("encodes taskId and flowId once in path", async () => {
    await fetchTraceReplay("TASK-1", "FLOW-A");
    expect(_requests).toHaveLength(1);
    const req = _requests[0];
    expect(req.url).toContain("TASK-1");
    expect(req.url).toContain("FLOW-A");
    expect(req.url).not.toContain("25");
    expect(req.params).toEqual({});
  });

  it("adds optional trace_id as query param", async () => {
    await fetchTraceReplay("T1", "F1", "trace-abc");
    expect(_requests).toHaveLength(1);
    const req = _requests[0];
    expect(req.params).toEqual({ trace_id: "trace-abc" });
  });

  it("omits trace_id param when undefined", async () => {
    await fetchTraceReplay("T1", "F1", undefined);
    expect(_requests).toHaveLength(1);
    const req = _requests[0];
    expect(req.params).toEqual({});
  });

  it("encodes reserved characters in path once", async () => {
    await fetchTraceReplay("T/A#S?K", "F&L=OW");
    expect(_requests).toHaveLength(1);
    const req = _requests[0];
    const taskEncoded = encodeURIComponent("T/A#S?K");
    const flowEncoded = encodeURIComponent("F&L=OW");
    expect(req.url).toContain(taskEncoded);
    expect(req.url).toContain(flowEncoded);
    // Each reserved char encoded exactly once.
    expect(req.url).toContain("%2F");
    expect(req.url).toContain("%23");
    expect(req.url).toContain("%26");
    expect(req.url).toContain("%3D");
    // No double-encoding: encoded substrings appear only as many times as expected.
    expect(req.url.match(/%2F/g)?.length).toBe(1);
    expect(req.url.match(/%26/g)?.length).toBe(1);
  });

  it("encodes trace_id in query params via Axios serialization", async () => {
    await fetchTraceReplay("T1", "F1", "t/a#b?c&d");
    expect(_requests).toHaveLength(1);
    const req = _requests[0];
    expect(req.params).toEqual({ trace_id: "t/a#b?c&d" });
  });
});
