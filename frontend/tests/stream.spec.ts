import { afterEach, describe, expect, it, vi } from "vitest";

import { streamReconcile } from "../src/api/stream";
import type { AgentStreamEvent } from "../src/types/api";
import { setToken } from "../src/composables/useAuth";

const localStorage = createStorage();

Object.defineProperty(window, "localStorage", { configurable: true, value: localStorage });

function createStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => values.set(key, value),
  };
}

function event(event_type: AgentStreamEvent["event_type"], seq: number): AgentStreamEvent {
  return {
    schema_version: "1.1",
    event_type,
    seq,
    task_id: event_type === "task_done" ? "TASK-1" : "PENDING",
    flow_id: null,
    ts: "2026-06-15T00:00:00Z",
    payload:
      event_type === "task_done"
        ? {
            status: "COMPLETED",
            total_bank_rows: 1,
            total_clear_rows: 1,
            auto_fixed_rows: 1,
            pending_ai_rows: 0,
            pending_human_rows: 0,
          }
        : { scenario_type: "BANK_ENTERPRISE" },
  };
}

function frame(streamEvent: AgentStreamEvent): string {
  return `data: ${JSON.stringify(streamEvent)}\n\n`;
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

function params() {
  return {
    bankFile: new File(["bank"], "bank.xlsx"),
    clearFile: new File(["clear"], "clear.xlsx"),
    scenarioType: "BANK_ENTERPRISE",
  };
}

describe("streamReconcile", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("parses a single SSE frame split across two chunks", async () => {
    const taskStarted = frame(event("task_started", 0));
    const received: AgentStreamEvent[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(streamFrom([taskStarted.slice(0, 18), taskStarted.slice(18)]))),
    );

    await streamReconcile(params(), { onEvent: (streamEvent) => received.push(streamEvent) });

    expect(received).toHaveLength(1);
    expect(received[0].event_type).toBe("task_started");
  });

  it("parses two SSE frames delivered in one chunk and calls onDone for task_done", async () => {
    const taskStarted = event("task_started", 0);
    const taskDone = event("task_done", 1);
    const received: AgentStreamEvent[] = [];
    const done = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(streamFrom([frame(taskStarted) + frame(taskDone)]))),
    );

    await streamReconcile(params(), {
      onEvent: (streamEvent) => received.push(streamEvent),
      onDone: done,
    });

    expect(received.map((streamEvent) => streamEvent.event_type)).toEqual([
      "task_started",
      "task_done",
    ]);
    expect(done).toHaveBeenCalledWith(taskDone);
  });

  it("reports non-2xx responses through onError", async () => {
    const onError = vi.fn();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 500 })));

    await expect(streamReconcile(params(), { onEvent: vi.fn(), onError })).rejects.toThrow(
      "流式请求失败",
    );

    expect(onError).toHaveBeenCalledWith(expect.any(Error));
  });

  it("sends stream form fields with the Bearer token", async () => {
    setToken("signed-token");
    const fetchMock = vi.fn(async () => new Response(streamFrom([])));
    vi.stubGlobal("fetch", fetchMock);

    await streamReconcile(params(), { onEvent: vi.fn() });

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const form = init.body as FormData;
    expect(url).toBe("/api/v1/reconcile/stream");
    expect(init.headers).toMatchObject({ Authorization: "Bearer signed-token" });
    expect(form.get("bank_file")).toBeInstanceOf(File);
    expect(form.get("clear_file")).toBeInstanceOf(File);
    expect(form.get("scenario_type")).toBe("BANK_ENTERPRISE");
  });

  it("stops reading after abort", async () => {
    const abortController = new AbortController();
    const taskStarted = frame(event("task_started", 0));
    const extraEvent = frame(event("hook", 1));
    const received: AgentStreamEvent[] = [];
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      pull(controller) {
        if (!received.length) {
          controller.enqueue(encoder.encode(taskStarted));
          return;
        }
        controller.enqueue(encoder.encode(extraEvent));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(body)));

    await streamReconcile(
      params(),
      {
        onEvent: (streamEvent) => {
          received.push(streamEvent);
          abortController.abort();
        },
      },
      abortController.signal,
    );

    expect(received.map((streamEvent) => streamEvent.event_type)).toEqual(["task_started"]);
  });
});
