import { apiGet } from "./client";
import type { DashboardMetrics } from "../types/api";

export function getDashboardMetrics(): Promise<DashboardMetrics> {
  return apiGet<DashboardMetrics>("/metrics/dashboard");
}
