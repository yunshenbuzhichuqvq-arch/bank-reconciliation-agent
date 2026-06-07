import { createRouter, createWebHistory } from "vue-router";

import DashboardPage from "../pages/DashboardPage.vue";
import LedgerPage from "../pages/LedgerPage.vue";
import ReviewPage from "../pages/ReviewPage.vue";
import UploadPage from "../pages/UploadPage.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/upload" },
    { path: "/upload", component: UploadPage },
    { path: "/tasks/:taskId", component: DashboardPage },
    { path: "/ledger", component: LedgerPage },
    { path: "/review", component: ReviewPage },
  ],
});
