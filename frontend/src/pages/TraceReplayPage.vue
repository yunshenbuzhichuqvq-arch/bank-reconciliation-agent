<script setup lang="ts">
import { ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { fetchTraceReplay } from "../api/trace";
import type { TraceReplayData, TraceRunSummary } from "../types/trace";
import type { ApiError } from "../api/client";
import TraceTimeline from "../components/TraceTimeline.vue";

const route = useRoute();
const router = useRouter();

const loading = ref(true);
const error = ref<string | null>(null);
const data = ref<TraceReplayData | null>(null);
const selectedTraceId = ref<string | undefined>(undefined);

async function load(taskId: string, flowId: string, traceId?: string) {
  loading.value = true;
  error.value = null;
  try {
    data.value = await fetchTraceReplay(taskId, flowId, traceId);
  } catch (err: unknown) {
    const apiError = err as ApiError;
    if (apiError?.status === 404) {
      error.value = "任务或执行记录未找到";
    } else {
      error.value = apiError?.message ?? "加载执行轨迹失败";
    }
    data.value = null;
  } finally {
    loading.value = false;
  }
}

function selectRun(run: TraceRunSummary) {
  selectedTraceId.value = run.trace_id;
  load(route.params.taskId as string, route.params.flowId as string, run.trace_id);
}

function statusLabel(): string {
  const status = data.value?.replay_status;
  if (status === "IN_PROGRESS") return "任务处理中，暂无执行轨迹";
  if (status === "TRACE_NOT_AVAILABLE") return "该流程暂无执行轨迹记录";
  return "";
}

function back() {
  if (window.history.length > 1) {
    router.back();
  } else {
    router.push("/ledger");
  }
}

watch(
  () => [route.params.taskId as string, route.params.flowId as string],
  ([taskId, flowId]) => {
    if (taskId && flowId) {
      selectedTraceId.value = undefined;
      data.value = null;
      load(taskId, flowId);
    }
  },
  { immediate: true },
);
</script>

<template>
  <div class="replay-page">
    <header class="replay-page__bar">
      <button class="btn-back" @click="back" aria-label="返回">← 返回</button>
      <h1 class="replay-page__title">执行轨迹</h1>
      <p class="replay-page__id">{{ route.params.taskId }} / {{ route.params.flowId }}</p>
    </header>

    <div v-if="loading" class="replay-page__state" role="status">加载中...</div>

    <div v-else-if="error" class="replay-page__state replay-page__state--error" role="alert">
      {{ error }}
    </div>

    <div v-else-if="data && data.replay_status !== 'AVAILABLE'" class="replay-page__state" role="status">
      {{ statusLabel() }}
    </div>

    <template v-else-if="data">
      <section v-if="data.runs.length > 1" class="replay-page__runs">
        <label class="replay-page__runs-label">历史执行:</label>
        <div class="replay-page__run-list">
          <button
            v-for="run in data.runs"
            :key="run.trace_id"
            class="run-chip"
            :class="{ 'run-chip--active': (selectedTraceId ?? data.selected_trace_id) === run.trace_id }"
            @click="selectRun(run)"
          >
            <span>{{ new Date(run.started_at).toLocaleString("zh-CN") }}</span>
            <span class="run-chip__outcome">{{ run.outcome ?? run.status }}</span>
          </button>
        </div>
      </section>

      <section class="replay-page__summary">
        <span>共 {{ data.execution_count }} 次执行</span>
        <span v-if="data.total_tokens">Token: {{ data.total_tokens }}</span>
        <span v-if="data.prompt_tokens">(输入 {{ data.prompt_tokens }} / 输出 {{ data.completion_tokens }})</span>
      </section>

      <TraceTimeline :spans="data.spans" />
    </template>
  </div>
</template>

<style scoped>
.replay-page {
  display: grid;
  gap: var(--space-6);
  padding: var(--space-6);
  max-width: 960px;
  margin: 0 auto;
}

.replay-page__bar {
  display: flex;
  gap: var(--space-4);
  align-items: baseline;
  flex-wrap: wrap;
}

.btn-back {
  background: none;
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  padding: var(--space-1) var(--space-3);
  color: var(--color-primary);
  cursor: pointer;
  font-size: 14px;
}

.replay-page__title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text);
}

.replay-page__id {
  margin: 0;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: 13px;
}

.replay-page__state {
  padding: var(--space-10);
  text-align: center;
  color: var(--color-text-muted);
  font-size: 15px;
}

.replay-page__state--error {
  color: var(--color-danger);
}

.replay-page__runs {
  display: grid;
  gap: var(--space-2);
}

.replay-page__runs-label {
  font-size: 13px;
  color: var(--color-text-muted);
}

.replay-page__run-list {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.run-chip {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-1) var(--space-3);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-full);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  font-size: 12px;
  font-family: var(--font-mono);
}

.run-chip--active {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.run-chip__outcome {
  color: var(--color-text-muted);
  font-size: 11px;
}

.replay-page__summary {
  display: flex;
  gap: var(--space-4);
  color: var(--color-text-muted);
  font-size: 13px;
  font-family: var(--font-mono);
}

@media (max-width: 640px) {
  .replay-page { padding: var(--space-4); }
}
</style>
