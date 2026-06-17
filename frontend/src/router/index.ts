import { createMemoryHistory, createRouter, createWebHistory } from "vue-router";

import DashboardPage from "../pages/DashboardPage.vue";
import LedgerPage from "../pages/LedgerPage.vue";
import MetricsPage from "../pages/MetricsPage.vue";
import ReviewPage from "../pages/ReviewPage.vue";
import UploadPage from "../pages/UploadPage.vue";
import WorkbenchPage from "../pages/WorkbenchPage.vue";

export const router = createRouter({
  history: typeof window === "undefined" ? createMemoryHistory() : createWebHistory(),
  routes: [
    { path: "/", redirect: "/upload" },
    { path: "/upload", component: UploadPage },
    { path: "/workbench", component: WorkbenchPage },
    { path: "/tasks/:taskId", component: DashboardPage },
    { path: "/metrics", component: MetricsPage },
    { path: "/ledger", component: LedgerPage },
    { path: "/review", component: ReviewPage },
  ],
});
