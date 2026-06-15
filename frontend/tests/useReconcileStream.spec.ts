import { describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import { useReconcileStream } from "../src/composables/useReconcileStream";
import { streamReconcile } from "../src/api/stream";
import type { AgentStreamEvent, StreamPayload } from "../src/types/api";
import type { StreamHandlers, StreamParams } from "../src/api/stream";

vi.mock("../src/api/stream", () => ({
  streamReconcile: vi.fn(),
}));

const streamReconcileMock = vi.mocked(streamReconcile);

function params(): StreamParams {
  return {
    bankFile: new File(["bank"], "bank.xlsx"),
    clearFile: new File(["clear"], "clear.xlsx"),
    scenarioType: "BANK_ENTERPRISE",
  };
}

function streamEvent(
  event_type: AgentStreamEvent["event_type"],
  seq: number,
  payload: StreamPayload,
): AgentStreamEvent {
  return {
    schema_version: "1.0",
    event_type,
    seq,
    task_id: event_type === "task_done" ? "TASK-1" : "PENDING",
    flow_id: null,
    ts: "2026-06-15T00:00:00Z",
    payload,
  };
}

describe("useReconcileStream", () => {
  it("accumulates events and stores task_done result", async () => {
    const taskStarted = streamEvent("task_started", 0, { scenario_type: "BANK_ENTERPRISE" });
    const taskDone = streamEvent("task_done", 1, {
      status: "COMPLETED",
      total_bank_rows: 2,
      total_clear_rows: 2,
      auto_fixed_rows: 1,
      pending_ai_rows: 0,
      pending_human_rows: 1,
    });
    streamReconcileMock.mockImplementationOnce(async (_params, handlers) => {
      expect(stream.status.value).toBe("streaming");
      handlers.onEvent(taskStarted);
      handlers.onEvent(taskDone);
      handlers.onDone?.(taskDone);
    });
    const stream = useReconcileStream();

    expect(stream.status.value).toBe("idle");
    await stream.start(params());

    expect(stream.status.value).toBe("done");
    expect(stream.events.value).toEqual([taskStarted, taskDone]);
    expect(stream.result.value).toEqual(taskDone.payload);
    expect(stream.error.value).toBeNull();
  });

  it("sets error state when the stream reports an error", async () => {
    streamReconcileMock.mockImplementationOnce(async (_params, handlers) => {
      handlers.onError?.(new Error("stream failed"));
    });
    const stream = useReconcileStream();

    await stream.start(params());

    expect(stream.status.value).toBe("error");
    expect(stream.error.value).toBe("stream failed");
  });

  it("aborts the active stream and resets status to idle", async () => {
    let receivedSignal: AbortSignal | undefined;
    streamReconcileMock.mockImplementationOnce(
      async (_params: StreamParams, _handlers: StreamHandlers, signal?: AbortSignal) => {
        receivedSignal = signal;
        await new Promise(() => undefined);
      },
    );
    const stream = useReconcileStream();

    void stream.start(params());
    await nextTick();
    stream.abort();

    expect(receivedSignal?.aborted).toBe(true);
    expect(stream.status.value).toBe("idle");
  });
});
