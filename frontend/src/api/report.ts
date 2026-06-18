import { apiGet } from "./client";
import type { TaskReport } from "../types/api";

export function getTaskReport(taskId: string): Promise<TaskReport> {
  return apiGet<TaskReport>(`/reconcile/${encodeURIComponent(taskId)}/report`);
}
