import { apiGet, apiPost, apiUpload } from "./client";
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

export function getTaskStatus(taskId:string):Promise<TaskStatus> {
  return apiGet<TaskStatus>(`/reconcile/${taskId}/status`);
}

export function getTaskExceptions(taskId:string):Promise<ExceptionList> {
  return apiGet<ExceptionList>(`/reconcile/${taskId}/exceptions`);
}
