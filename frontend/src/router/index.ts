import { createMemoryHistory, createRouter, createWebHistory } from "vue-router";

import DashboardPage from "../pages/DashboardPage.vue";
import LedgerPage from "../pages/LedgerPage.vue";
import LoginPage from "../pages/LoginPage.vue";
import MetricsPage from "../pages/MetricsPage.vue";
import ReportPage from "../pages/ReportPage.vue";
import ReviewPage from "../pages/ReviewPage.vue";
import UploadPage from "../pages/UploadPage.vue";
import WorkbenchPage from "../pages/WorkbenchPage.vue";
import { isAuthenticated } from "../composables/useAuth";

const PUBLIC_ROUTES = new Set(["/login"]);

export const router = createRouter({
  history: typeof window === "undefined" ? createMemoryHistory() : createWebHistory(),
  routes: [
    { path: "/login", component: LoginPage },
    { path: "/", redirect: "/upload" },
    { path: "/upload", component: UploadPage },
    { path: "/workbench", component: WorkbenchPage },
    { path: "/tasks/:taskId", component: DashboardPage },
    { path: "/metrics", component: MetricsPage },
    { path: "/reports", component: ReportPage },
    { path: "/ledger", component: LedgerPage },
    { path: "/review", component: ReviewPage },
  ],
});

router.beforeEach((to) => {
  const authenticated = isAuthenticated();
  if (!PUBLIC_ROUTES.has(to.path) && !authenticated) {
    return "/login";
  }
  if (to.path === "/login" && authenticated) {
    return "/";
  }
  return true;
});
