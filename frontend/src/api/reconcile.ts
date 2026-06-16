import { apiGet, apiPost, apiUpload, getDefaultHeaders } from "./client";
import { readSseBody, type StreamHandlers } from "./stream";
import type { ExceptionList, TaskStatus, UploadResult } from "../types/api";
import type { ScenarioType } from "../constants/enums";

export function uploadReconciliation(
  bankFile:File,
  clearFile:File,
  scenarioType:ScenarioType = "BANK_ENTERPRISE",
):Promise<UploadResult> {
  const form = new FormData();
  form.append("bank_file", bankFile);
  form.append("clear_file", clearFile);
  form.append("scenario_type", scenarioType);
  return apiUpload<UploadResult>("/reconcile/upload", form);
}

export function startReconciliation(taskId:string):Promise<{task_id:string;status:string}> {
  return apiPost<{task_id:string;status:string}>(`/reconcile/${taskId}/start`);
}

export function startLiveReconciliation(taskId:string):Promise<{task_id:string;status:string}> {
  return apiPost<{task_id:string;status:string}>(`/reconcile/${taskId}/start-live`);
}

export function getTaskStatus(taskId:string):Promise<TaskStatus> {
  return apiGet<TaskStatus>(`/reconcile/${taskId}/status`);
}

export function getTaskExceptions(taskId:string):Promise<ExceptionList> {
  return apiGet<ExceptionList>(`/reconcile/${taskId}/exceptions`);
}

export type TaskEventHandlers = StreamHandlers;

export async function streamTaskEvents(
  taskId:string,
  handlers:TaskEventHandlers,
  signal?:AbortSignal,
):Promise<void> {
  try {
    const response = await fetch(`/api/v1/reconcile/${taskId}/events`, {
      method: "GET",
      headers: getDefaultHeaders(),
      signal,
    });

    if (!response.ok) {
      throw new Error(`任务事件流请求失败 (${response.status})`);
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

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
