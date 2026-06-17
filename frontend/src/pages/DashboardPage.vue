<script setup lang="ts">
import { computed, onMounted, onServerPrefetch, ref } from "vue";
import { useRoute } from "vue-router";

import { getTaskExceptions, getTaskStatus, startLiveReconciliation } from "../api/reconcile";
import type { ApiError } from "../api/client";
import type { ExceptionList, TaskStatus } from "../types/api";
import { ERROR_TYPE_LABEL } from "../constants/enums";
import { useTaskEventStream } from "../composables/useTaskEventStream";
import BranchDistribution from "../components/dashboard/BranchDistribution.vue";
import StatCard from "../components/dashboard/StatCard.vue";
import BaseButton from "../components/ui/BaseButton.vue";
import BaseCard from "../components/ui/BaseCard.vue";
import EmptyState from "../components/ui/EmptyState.vue";
import PageHeader from "../components/ui/PageHeader.vue";
import StatusBadge from "../components/ui/StatusBadge.vue";

const route = useRoute();
const taskId = computed(() => String(route.params.taskId));

const status = ref<TaskStatus | null>(null);
const exceptions = ref<ExceptionList | null>(null);
const statusLoading = ref(false);
const exceptionsLoading = ref(false);
const startLoading = ref(false);
const errorText = ref("");
const taskStream = useTaskEventStream();

const isLoading = computed(() => statusLoading.value || exceptionsLoading.value);
const isAiRunning = computed(() => status.value?.status === "AI_RUNNING" || taskStream.status.value === "streaming");

// MVP 近似：auto_fixed_rows / (auto_fixed_rows + exceptions.total)，分母为 0 显示 —。
const autoRate = computed(() => {
  if (!status.value || !exceptions.value) {
    return null;
  }
  const denominator = status.value.auto_fixed_rows + exceptions.value.total;
  if (!denominator) {
    return null;
  }
  return status.value.auto_fixed_rows / denominator;
});

const stats = computed(() => {
  if (!status.value) {
    return [];
  }
  const progress = taskStream.progress.value;
  return [
    { label: "自动修复", value: progress?.auto_fixed ?? status.value.auto_fixed_rows },
    { label: "AI 已处理", value: progress?.processed ?? status.value.ai_processed_rows },
    { label: "待人工复核", value: progress?.pending_human ?? status.value.pending_human_rows },
    { label: "未解决", value: progress?.unresolved ?? status.value.unresolved_rows },
    { label: "自动平账率", value: formatRate(autoRate.value), note: "按异常总数近似计算" },
  ];
});

const distribution = computed(() => {
  const progressDist = taskStream.progress.value?.exception_dist;
  if (progressDist) {
    return Object.entries(progressDist)
      .map(([type, count]) => ({
        type,
        count,
        label: ERROR_TYPE_LABEL[type] ?? type,
      }))
      .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
  }

  const counts = new Map<string, number>();
  for (const item of exceptions.value?.items ?? []) {
    counts.set(item.error_type, (counts.get(item.error_type) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([type, count]) => ({
      type,
      count,
      label: ERROR_TYPE_LABEL[type] ?? type,
    }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
});

const distributionTotal = computed(() =>
  taskStream.progress.value
    ? Object.values(taskStream.progress.value.exception_dist).reduce((sum, count) => sum + count, 0)
    : (exceptions.value?.total ?? 0),
);

onMounted(() => {
  refreshData();
});
onServerPrefetch(() => refreshData());

async function refreshData() {
  errorText.value = "";
  statusLoading.value = true;
  exceptionsLoading.value = true;

  const statusRequest = getTaskStatus(taskId.value)
    .then((data) => {
      status.value = data;
    })
    .catch((error) => {
      errorText.value = errorMessage(error);
      status.value = null;
    })
    .finally(() => {
      statusLoading.value = false;
    });

  const exceptionsRequest = getTaskExceptions(taskId.value)
    .then((data) => {
      exceptions.value = data;
    })
    .catch((error) => {
      errorText.value = errorMessage(error);
      exceptions.value = null;
    })
    .finally(() => {
      exceptionsLoading.value = false;
    });

  await Promise.allSettled([statusRequest, exceptionsRequest]);
}

async function startAudit() {
  if (startLoading.value || isAiRunning.value) {
    return;
  }

  startLoading.value = true;
  errorText.value = "";

  try {
    await startLiveReconciliation(taskId.value);
    status.value = status.value ? { ...status.value, status: "AI_RUNNING" } : status.value;
    await taskStream.start(taskId.value);
    await refreshData();
  } catch (error) {
    errorText.value = taskStream.error.value ?? errorMessage(error);
  } finally {
    startLoading.value = false;
  }
}

function formatRate(value: number | null) {
  if (value === null) {
    return "—";
  }
  return `${Math.round(value * 100)}%`;
}

function errorMessage(error: unknown) {
  return (error as ApiError).message ?? "请求失败";
}
</script>

<template>
  <PageHeader
    title="任务看板"
    :description="`任务 ${taskId}`"
  >
    <template #actions>
      <BaseButton
        variant="secondary"
        :loading="isLoading && !startLoading"
        @click="refreshData"
      >
        刷新
      </BaseButton>
      <BaseButton
        :disabled="isAiRunning"
        :loading="startLoading"
        @click="startAudit"
      >
        {{ isAiRunning ? "已启动" : "启动 AI 审计" }}
      </BaseButton>
    </template>
  </PageHeader>

  <div class="dashboard-page">
    <div v-if="errorText" class="dashboard-page__error" role="alert">
      <strong>数据加载失败</strong>
      <span>{{ errorText }}</span>
    </div>

    <div v-if="isLoading && !status" class="stats-grid" aria-label="加载任务指标">
      <div v-for="index in 5" :key="index" class="stat-skeleton" />
    </div>
    <div v-else-if="status" class="stats-grid">
      <BaseCard class="status-card">
        <p class="status-card__label">当前状态</p>
        <StatusBadge :value="status.status" />
      </BaseCard>
      <StatCard
        v-for="item in stats"
        :key="item.label"
        :label="item.label"
        :value="item.value"
        :note="item.note"
      />
    </div>
    <EmptyState
      v-else-if="!isLoading"
      title="未能读取任务状态"
      description="请确认任务 ID 是否存在，或稍后刷新。"
    />

    <BaseCard title="异常类型分布">
      <div v-if="exceptionsLoading && !exceptions" class="distribution-skeleton">
        <span v-for="index in 4" :key="index" />
      </div>
      <BranchDistribution
        v-else
        :items="distribution"
        :total="distributionTotal"
      />
    </BaseCard>
  </div>
</template>

<style scoped>
.dashboard-page {
  display: grid;
  gap: var(--space-6);
}

.dashboard-page__error {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-5);
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, var(--color-surface));
  border: 1px solid color-mix(in srgb, var(--color-danger) 28%, var(--color-border-soft));
  border-radius: var(--radius-md);
}

.dashboard-page__error strong,
.dashboard-page__error span {
  font-size: 14px;
  line-height: 1.5;
}

.dashboard-page__error span {
  font-family: var(--font-mono);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
}

.status-card :deep(.base-card__body) {
  display: grid;
  align-content: start;
  gap: var(--space-3);
  min-height: 128px;
}

.status-card__label {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.stat-skeleton,
.distribution-skeleton span {
  position: relative;
  overflow: hidden;
  background: var(--color-surface-muted);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-lg);
}

.stat-skeleton {
  min-height: 128px;
}

.distribution-skeleton {
  display: grid;
  gap: var(--space-4);
}

.distribution-skeleton span {
  height: 36px;
}

.stat-skeleton::after,
.distribution-skeleton span::after {
  position: absolute;
  inset: 0;
  content: "";
  background: linear-gradient(
    90deg,
    transparent,
    color-mix(in srgb, var(--color-surface) 66%, transparent),
    transparent
  );
  animation: shimmer 1.2s infinite;
}

@keyframes shimmer {
  from {
    transform: translateX(-100%);
  }

  to {
    transform: translateX(100%);
  }
}

@media (max-width: 960px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
