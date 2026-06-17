import { afterEach, describe, expect, it, vi } from "vitest";

import { startLiveReconciliation, streamTaskEvents, uploadReconciliation } from "../src/api/reconcile";
import type { AgentStreamEvent } from "../src/types/api";

const apiUpload = vi.hoisted(() =>
  vi.fn(async (_url: string, _form: FormData) => ({ task_id: "TASK-1" })),
);
const apiPost = vi.hoisted(() =>
  vi.fn(async (_url: string) => ({ task_id: "TASK-1", status: "AI_RUNNING" })),
);

vi.mock("../src/api/client", () => ({
  apiGet: vi.fn(),
  apiPost,
  apiUpload,
  getDefaultHeaders: () => ({ "X-User-ID": "demo_user" }),
}));

function file(name: string) {
  return new File(["x"], name, {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

function streamFrom(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

function frame(streamEvent: AgentStreamEvent): string {
  return `data: ${JSON.stringify(streamEvent)}\n\n`;
}

describe("uploadReconciliation", () => {
  afterEach(() => {
    apiUpload.mockClear();
  });

  it("uses BANK_ENTERPRISE as the default scenario_type", async () => {
    await uploadReconciliation(file("bank.xlsx"), file("clear.xlsx"));

    const form = apiUpload.mock.calls[0][1] as FormData;
    expect(form.get("scenario_type")).toBe("BANK_ENTERPRISE");
  });

  it("appends the selected scenario_type", async () => {
    await uploadReconciliation(file("bank.xlsx"), file("clear.xlsx"), "BANK_CLEARING");

    const form = apiUpload.mock.calls[0][1] as FormData;
    expect(form.get("scenario_type")).toBe("BANK_CLEARING");
  });

  it("starts a live reconciliation task through start-live", async () => {
    await startLiveReconciliation("TASK-1");

    expect(apiPost).toHaveBeenCalledWith("/reconcile/TASK-1/start-live");
  });

  it("streams task_progress events from the by-taskId endpoint", async () => {
    const progressEvent: AgentStreamEvent = {
      schema_version: "1.1",
      event_type: "task_progress",
      seq: 1,
      task_id: "TASK-1",
      flow_id: null,
      ts: "2026-06-15T00:00:00Z",
      payload: {
        processed: 2,
        total: 4,
        auto_fixed: 1,
        pending_ai: 1,
        pending_human: 1,
        unresolved: 1,
        exception_dist: { AMOUNT_MISMATCH: 2 },
      },
    };
    const fetchMock = vi.fn(async () => new Response(streamFrom([frame(progressEvent)])));
    vi.stubGlobal("fetch", fetchMock);
    const received: AgentStreamEvent[] = [];

    await streamTaskEvents("TASK-1", { onEvent: (event) => received.push(event) });

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/reconcile/TASK-1/events");
    expect(init.headers).toMatchObject({ "X-User-ID": "demo_user" });
    expect(received).toEqual([progressEvent]);
  });
});
