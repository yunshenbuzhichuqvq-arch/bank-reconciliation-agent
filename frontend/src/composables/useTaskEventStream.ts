import { readonly, ref, type Ref } from "vue";

import { streamTaskEvents } from "../api/reconcile";
import type { AgentStreamEvent, TaskProgressPayload } from "../types/api";
import type { StreamStatus } from "./useReconcileStream";

export interface UseTaskEventStream {
  events: Readonly<Ref<readonly AgentStreamEvent[]>>;
  progress: Readonly<Ref<TaskProgressPayload | null>>;
  status: Readonly<Ref<StreamStatus>>;
  error: Readonly<Ref<string | null>>;
  start: (taskId:string) => Promise<void>;
  abort: () => void;
}

export function useTaskEventStream(): UseTaskEventStream {
  const events = ref<AgentStreamEvent[]>([]);
  const progress = ref<TaskProgressPayload | null>(null);
  const status = ref<StreamStatus>("idle");
  const error = ref<string | null>(null);
  let controller: AbortController | null = null;

  async function start(taskId:string): Promise<void> {
    controller?.abort();
    controller = new AbortController();
    events.value = [];
    progress.value = null;
    error.value = null;
    status.value = "streaming";

    try {
      await streamTaskEvents(
        taskId,
        {
          onEvent: (event) => {
            events.value.push(event);
            if (event.event_type === "task_progress") {
              progress.value = event.payload as TaskProgressPayload;
            }
          },
          onDone: () => {
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
    progress: readonly(progress),
    status: readonly(status),
    error: readonly(error),
    start,
    abort,
  };
}
