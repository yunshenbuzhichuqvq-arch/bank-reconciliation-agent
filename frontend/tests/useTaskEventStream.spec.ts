import { describe, expect, it, vi } from "vitest";

import { useTaskEventStream } from "../src/composables/useTaskEventStream";
import { streamTaskEvents } from "../src/api/reconcile";
import type { AgentStreamEvent } from "../src/types/api";
import type { TaskEventHandlers } from "../src/api/reconcile";

vi.mock("../src/api/reconcile", () => ({
  streamTaskEvents: vi.fn(),
}));

const streamTaskEventsMock = vi.mocked(streamTaskEvents);

function taskProgressEvent(): AgentStreamEvent {
  return {
    schema_version: "1.1",
    event_type: "task_progress",
    seq: 1,
    task_id: "TASK-1",
    flow_id: null,
    ts: "2026-06-15T00:00:00Z",
    payload: {
      processed: 3,
      total: 5,
      auto_fixed: 2,
      pending_ai: 1,
      pending_human: 1,
      unresolved: 1,
      exception_dist: { AMOUNT_MISMATCH: 2, MISSING_CLEAR: 1 },
    },
  };
}

describe("useTaskEventStream", () => {
  it("consumes task_progress events from the task event stream", async () => {
    const progress = taskProgressEvent();
    streamTaskEventsMock.mockImplementationOnce(async (_taskId: string, handlers: TaskEventHandlers) => {
      handlers.onEvent(progress);
    });
    const stream = useTaskEventStream();

    await stream.start("TASK-1");

    expect(streamTaskEventsMock).toHaveBeenCalledWith("TASK-1", expect.any(Object), expect.any(AbortSignal));
    expect(stream.status.value).toBe("streaming");
    expect(stream.progress.value).toEqual(progress.payload);
    expect(stream.events.value).toEqual([progress]);
  });
});
