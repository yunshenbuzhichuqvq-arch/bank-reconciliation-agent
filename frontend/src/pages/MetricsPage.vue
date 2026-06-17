<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, onServerPrefetch, ref, watch } from "vue";
import { BarChart, LineChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { init, use, type ECharts, type EChartsCoreOption } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

import { getDashboardMetrics } from "../api/metrics";
import type { ApiError } from "../api/client";
import type { DashboardMetrics, OfflineMetrics } from "../types/api";
import { ERROR_TYPE_LABEL } from "../constants/enums";
import BaseButton from "../components/ui/BaseButton.vue";
import BaseCard from "../components/ui/BaseCard.vue";
import EmptyState from "../components/ui/EmptyState.vue";
import PageHeader from "../components/ui/PageHeader.vue";
import StatCard from "../components/dashboard/StatCard.vue";

use([BarChart, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

const metrics = ref<DashboardMetrics | null>(null);
const loading = ref(false);
const errorText = ref("");
const exceptionChartRef = ref<HTMLElement | null>(null);
const fallbackChartRef = ref<HTMLElement | null>(null);
const confidenceChartRef = ref<HTMLElement | null>(null);
const tokenChartRef = ref<HTMLElement | null>(null);
const chartInstances: ECharts[] = [];

const offlineMetrics = computed(() =>
  metrics.value?.offline && "evaluated_at" in metrics.value.offline
    ? (metrics.value.offline as OfflineMetrics)
    : null,
);
const isOfflineMissing = computed(() => metrics.value?.offline && "status" in metrics.value.offline);

const onlineStats = computed(() => {
  if (!metrics.value) {
    return [];
  }
  return [
    { label: "自动平账率", value: formatRate(metrics.value.online.auto_fix_rate) },
    { label: "待人工复核", value: metrics.value.online.pending_human_count },
    { label: "运行中任务", value: metrics.value.online.hung_count },
    { label: "Token 用量", value: metrics.value.online.total_tokens },
    { label: "LLM 成本", value: metrics.value.online.total_cost },
  ];
});

onMounted(async () => {
  await loadMetrics();
});
onServerPrefetch(() => loadMetrics());
onBeforeUnmount(() => {
  for (const chart of chartInstances) {
    chart.dispose();
  }
});

watch(metrics, () => {
  void nextTick(renderCharts);
});

async function loadMetrics() {
  loading.value = true;
  errorText.value = "";
  try {
    metrics.value = await getDashboardMetrics();
  } catch (error) {
    errorText.value = errorMessage(error);
    metrics.value = null;
  } finally {
    loading.value = false;
  }
}

function renderCharts() {
  if (!metrics.value || typeof window === "undefined") {
    return;
  }
  chartInstances.splice(0).forEach((chart) => chart.dispose());
  mountChart(exceptionChartRef.value, barOption("异常分布", labeledEntries(metrics.value.online.exception_dist)));
  mountChart(fallbackChartRef.value, pieOption("Fallback 路径", entries(metrics.value.online.fallback_dist)));
  mountChart(confidenceChartRef.value, pieOption("置信度", entries(metrics.value.online.confidence_dist)));
  mountChart(
    tokenChartRef.value,
    lineOption("Token 与成本", [
      ["Tokens", metrics.value.online.total_tokens],
      ["Cost", Number(metrics.value.online.total_cost)],
    ]),
  );
}

function mountChart(element: HTMLElement | null, option: EChartsCoreOption) {
  if (!element) {
    return;
  }
  const chart = init(element);
  chart.setOption(option);
  chartInstances.push(chart);
}

function labeledEntries(values: Record<string, number>): Array<[string, number]> {
  return Object.entries(values).map(([key, value]) => [ERROR_TYPE_LABEL[key] ?? key, value]);
}

function entries(values: Record<string, number>): Array<[string, number]> {
  return Object.entries(values);
}

function barOption(title: string, values: Array<[string, number]>): EChartsCoreOption {
  return {
    tooltip: {},
    grid: { left: 24, right: 16, top: 20, bottom: 48, containLabel: true },
    xAxis: { type: "category", data: values.map(([label]) => label), axisLabel: { rotate: 20 } },
    yAxis: { type: "value" },
    series: [{ name: title, type: "bar", data: values.map(([, value]) => value), barMaxWidth: 34 }],
  };
}

function pieOption(title: string, values: Array<[string, number]>): EChartsCoreOption {
  return {
    tooltip: { trigger: "item" },
    legend: { bottom: 0, type: "scroll" },
    series: [
      {
        name: title,
        type: "pie",
        radius: ["42%", "68%"],
        center: ["50%", "42%"],
        data: values.map(([name, value]) => ({ name, value })),
      },
    ],
  };
}

function lineOption(title: string, values: Array<[string, number]>): EChartsCoreOption {
  return {
    tooltip: {},
    grid: { left: 24, right: 18, top: 20, bottom: 36, containLabel: true },
    xAxis: { type: "category", data: values.map(([label]) => label) },
    yAxis: { type: "value" },
    series: [{ name: title, type: "line", smooth: true, data: values.map(([, value]) => value) }],
  };
}

function formatRate(value: number) {
  return `${Number((value * 100).toFixed(1))}%`;
}

function errorMessage(error: unknown) {
  return (error as ApiError).message ?? "请求失败";
}
</script>

<template>
  <PageHeader
    title="量化指标"
    description="线上聚合、离线评测与暂无数据源指标"
  >
    <template #actions>
      <BaseButton variant="secondary" :loading="loading" @click="loadMetrics">
        刷新
      </BaseButton>
    </template>
  </PageHeader>

  <div class="metrics-page">
    <div v-if="errorText" class="metrics-page__error" role="alert">
      <strong>指标加载失败</strong>
      <span>{{ errorText }}</span>
    </div>

    <div v-if="loading && !metrics" class="metrics-page__skeleton" aria-label="加载指标">
      <span v-for="index in 8" :key="index" />
    </div>

    <template v-else-if="metrics">
      <section class="metrics-section" aria-labelledby="online-title">
        <h2 id="online-title">线上聚合</h2>
        <div class="metrics-page__stats">
          <StatCard
            v-for="item in onlineStats"
            :key="item.label"
            :label="item.label"
            :value="item.value"
          />
        </div>

        <div class="chart-grid">
          <BaseCard title="异常分布">
            <div ref="exceptionChartRef" class="chart-panel" role="img" aria-label="异常分布图表" />
          </BaseCard>
          <BaseCard title="Fallback 路径">
            <div ref="fallbackChartRef" class="chart-panel" role="img" aria-label="Fallback 路径图表" />
          </BaseCard>
          <BaseCard title="置信度分布">
            <div ref="confidenceChartRef" class="chart-panel" role="img" aria-label="置信度分布图表" />
          </BaseCard>
          <BaseCard title="Token 与成本">
            <div ref="tokenChartRef" class="chart-panel" role="img" aria-label="Token 与成本图表" />
          </BaseCard>
        </div>
      </section>

      <section class="metrics-section" aria-labelledby="offline-title">
        <h2 id="offline-title">离线评测</h2>
        <div v-if="offlineMetrics" class="metrics-page__stats">
          <StatCard label="Recall@5" :value="formatRate(offlineMetrics.rag_recall_at5)" />
          <StatCard label="MRR" :value="offlineMetrics.rag_mrr" />
          <StatCard label="Schema 符合率" :value="formatRate(offlineMetrics.schema_conformance_rate)" />
          <StatCard label="评测时间" :value="offlineMetrics.evaluated_at" />
        </div>
        <BaseCard v-else-if="isOfflineMissing">
          <EmptyState title="未运行评测" description="未发现离线评测快照，当前不展示评测数值。" />
        </BaseCard>
      </section>

      <section class="metrics-section" aria-labelledby="unavailable-title">
        <h2 id="unavailable-title">暂无数据源</h2>
        <div class="metrics-page__stats">
          <StatCard label="延迟指标" value="暂无数据源" />
          <StatCard label="Agent 准确率" value="暂无 Ground Truth" />
        </div>
      </section>
    </template>

    <EmptyState
      v-else-if="!loading"
      title="未能读取指标"
      description="请稍后刷新。"
    />
  </div>
</template>

<style scoped>
.metrics-page {
  display: grid;
  gap: var(--space-8);
}

.metrics-page__error {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-5);
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, var(--color-surface));
  border: 1px solid color-mix(in srgb, var(--color-danger) 28%, var(--color-border-soft));
  border-radius: var(--radius-md);
}

.metrics-page__error strong,
.metrics-page__error span {
  font-size: 14px;
  line-height: 1.5;
}

.metrics-section {
  display: grid;
  gap: var(--space-4);
}

.metrics-section h2 {
  margin: 0;
  color: var(--color-text);
  font-size: 18px;
  font-weight: 650;
  line-height: 1.4;
}

.metrics-page__stats {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--space-4);
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

.chart-panel {
  width: 100%;
  min-height: 280px;
}

.metrics-page__skeleton {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-4);
}

.metrics-page__skeleton span {
  min-height: 128px;
  background: var(--color-surface-muted);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-lg);
}

@media (max-width: 1120px) {
  .metrics-page__stats {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 820px) {
  .chart-grid,
  .metrics-page__skeleton {
    grid-template-columns: 1fr;
  }

  .metrics-page__stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .metrics-page__stats {
    grid-template-columns: 1fr;
  }
}
</style>
