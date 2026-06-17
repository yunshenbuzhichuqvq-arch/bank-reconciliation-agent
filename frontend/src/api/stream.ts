import { getDefaultHeaders } from "./client";
import type { AgentStreamEvent } from "../types/api";

const SUPPORTED_STREAM_SCHEMA_VERSIONS = new Set(["1.0", "1.1"]);

export interface StreamHandlers {
  onEvent: (event: AgentStreamEvent) => void;
  onDone?: (event: AgentStreamEvent) => void;
  onError?: (error: Error) => void;
}

export interface StreamParams {
  bankFile: File;
  clearFile: File;
  scenarioType: string;
}

export async function streamReconcile(
  params: StreamParams,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  try {
    const response = await fetch("/api/v1/reconcile/stream", {
      method: "POST",
      headers: getDefaultHeaders(),
      body: buildFormData(params),
      signal,
    });

    if (!response.ok) {
      throw new Error(`流式请求失败 (${response.status})`);
    }
    if (!response.body) {
      throw new Error("浏览器不支持流式响应");
    }

    await readSseBody(response.body, handlers, signal);
  } catch (error) {
    if (isAbortError(error) || signal?.aborted) {
      return;
    }
    const normalized = error instanceof Error ? error : new Error(String(error));
    handlers.onError?.(normalized);
    throw normalized;
  }
}

function buildFormData(params: StreamParams): FormData {
  const form = new FormData();
  form.append("bank_file", params.bankFile);
  form.append("clear_file", params.clearFile);
  form.append("scenario_type", params.scenarioType);
  return form;
}

export async function readSseBody(
  body: ReadableStream<Uint8Array>,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (!signal?.aborted) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      buffer = consumeFrames(buffer, handlers);
    }
  } finally {
    reader.releaseLock();
  }
}

function consumeFrames(buffer: string, handlers: StreamHandlers): string {
  let rest = buffer;
  let separatorIndex = rest.indexOf("\n\n");

  while (separatorIndex !== -1) {
    const rawFrame = rest.slice(0, separatorIndex);
    rest = rest.slice(separatorIndex + 2);
    parseFrame(rawFrame, handlers);
    separatorIndex = rest.indexOf("\n\n");
  }

  return rest;
}

function parseFrame(rawFrame: string, handlers: StreamHandlers): void {
  const data = rawFrame
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");

  if (!data) {
    return;
  }

  const event = JSON.parse(data) as AgentStreamEvent;
  if (!SUPPORTED_STREAM_SCHEMA_VERSIONS.has(event.schema_version)) {
    throw new Error(`不支持的流式事件版本: ${event.schema_version}`);
  }

  handlers.onEvent(event);
  if (event.event_type === "task_done") {
    handlers.onDone?.(event);
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
