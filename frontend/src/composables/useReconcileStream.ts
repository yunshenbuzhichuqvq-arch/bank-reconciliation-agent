import { readonly, ref, type Ref } from "vue";

import { streamReconcile, type StreamParams } from "../api/stream";
import type { AgentStreamEvent, StreamPayload } from "../types/api";

export type StreamStatus = "idle" | "streaming" | "done" | "error";

export interface UseReconcileStream {
  events: Readonly<Ref<readonly AgentStreamEvent[]>>;
  status: Readonly<Ref<StreamStatus>>;
  result: Readonly<Ref<StreamPayload | null>>;
  error: Readonly<Ref<string | null>>;
  start: (params: StreamParams) => Promise<void>;
  abort: () => void;
}

export function useReconcileStream(): UseReconcileStream {
  const events = ref<AgentStreamEvent[]>([]);
  const status = ref<StreamStatus>("idle");
  const result = ref<StreamPayload | null>(null);
  const error = ref<string | null>(null);
  let controller: AbortController | null = null;

  async function start(params: StreamParams): Promise<void> {
    controller = new AbortController();
    events.value = [];
    result.value = null;
    error.value = null;
    status.value = "streaming";

    try {
      await streamReconcile(
        params,
        {
          onEvent: (event) => {
            events.value.push(event);
          },
          onDone: (event) => {
            result.value = event.payload;
            status.value = "done";
          },
          onError: (streamError) => {
            error.value = streamError.message;
            status.value = "error";
          },
        },
        controller.signal,
      );
    } catch (streamError) {
      error.value = streamError instanceof Error ? streamError.message : String(streamError);
      status.value = "error";
    }
  }

  function abort(): void {
    controller?.abort();
    controller = null;
    status.value = "idle";
  }

  return {
    events: readonly(events),
    status: readonly(status),
    result: readonly(result),
    error: readonly(error),
    start,
    abort,
  };
}
