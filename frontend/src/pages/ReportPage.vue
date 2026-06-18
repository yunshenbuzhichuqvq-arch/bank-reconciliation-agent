<script setup lang="ts">
import { computed, ref } from "vue";

import { getTaskReport } from "../api/report";
import type { ApiError } from "../api/client";
import type { TaskReport } from "../types/api";
import { ERROR_TYPE_LABEL } from "../constants/enums";
import StatCard from "../components/dashboard/StatCard.vue";
import BaseButton from "../components/ui/BaseButton.vue";
import BaseCard from "../components/ui/BaseCard.vue";
import EmptyState from "../components/ui/EmptyState.vue";
import PageHeader from "../components/ui/PageHeader.vue";

const taskId = ref("");
const report = ref<TaskReport | null>(null);
const loading = ref(false);
const errorText = ref("");
const actionMessage = ref("");

const summaryStats = computed(() => {
  if (!report.value) {
    return [];
  }
  const metrics = report.value.metrics;
  return [
    { label: "来源 A", value: metrics.source_a_rows },
    { label: "来源 B", value: metrics.source_b_rows },
    { label: "自动平账率", value: formatRate(metrics.auto_fix_rate) },
    { label: "待人工复核", value: metrics.pending_human_count },
    { label: "差异金额", value: metrics.discrepancy_amount_total },
    { label: "Token 用量", value: metrics.total_tokens },
  ];
});

async function generateReport() {
  const normalizedTaskId = taskId.value.trim();
  actionMessage.value = "";
  if (!normalizedTaskId) {
    errorText.value = "请输入任务编号";
    return;
  }
  loading.value = true;
  errorText.value = "";
  try {
    report.value = await getTaskReport(normalizedTaskId);
  } catch (error) {
    report.value = null;
    errorText.value = (error as ApiError).message ?? "报告生成失败";
  } finally {
    loading.value = false;
  }
}

async function copyMarkdown() {
  if (!report.value) {
    return;
  }
  try {
    await navigator.clipboard.writeText(report.value.markdown);
    actionMessage.value = "Markdown 已复制";
  } catch {
    actionMessage.value = "复制失败，请使用下载功能";
  }
}

function downloadMarkdown() {
  if (!report.value) {
    return;
  }
  const blob = new Blob([report.value.markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${report.value.task_id}-audit-report.md`;
  anchor.click();
  URL.revokeObjectURL(url);
  actionMessage.value = "Markdown 已下载";
}

function formatRate(value: number) {
  return `${Number((value * 100).toFixed(1))}%`;
}

function entries(values: Record<string, number>, labels?: Record<string, string>) {
  return Object.entries(values).map(([key, value]) => ({
    key,
    label: labels?.[key] ?? key,
    value,
  }));
}
</script>

<template>
  <PageHeader title="报表审计" description="按任务实时生成可追溯的对账审计报告" />

  <div class="report-page">
    <BaseCard>
      <form class="report-form" @submit.prevent="generateReport">
        <label for="report-task-id">任务编号</label>
        <div class="report-form__controls">
          <input
            id="report-task-id"
            v-model="taskId"
            name="task-id"
            placeholder="例如 TASK-20260618-001"
            autocomplete="off"
          />
          <BaseButton :loading="loading" @click="generateReport">生成报告</BaseButton>
        </div>
        <p>报告按需实时生成，不保存历史版本。</p>
      </form>
    </BaseCard>

    <div v-if="errorText" class="report-page__error" role="alert">{{ errorText }}</div>

    <template v-if="report">
      <section class="report-meta" aria-label="报告信息">
        <div>
          <span>任务</span>
          <strong>{{ report.task_id }}</strong>
        </div>
        <div>
          <span>生成时间</span>
          <strong>{{ report.generated_at }}</strong>
        </div>
        <div>
          <span>叙述来源</span>
          <strong>{{ report.llm_used ? "ReportAgent" : "降级模板" }}</strong>
        </div>
        <div class="report-meta__actions">
          <BaseButton variant="secondary" @click="copyMarkdown">复制 Markdown</BaseButton>
          <BaseButton data-testid="download-report" @click="downloadMarkdown">下载 .md</BaseButton>
        </div>
      </section>
      <p v-if="actionMessage" class="report-page__feedback" role="status">{{ actionMessage }}</p>

      <section class="report-section" aria-labelledby="report-overview-title">
        <h2 id="report-overview-title">本批次概览</h2>
        <div class="report-stats">
          <StatCard
            v-for="item in summaryStats"
            :key="item.label"
            :label="item.label"
            :value="item.value"
          />
        </div>
      </section>

      <div class="report-grid">
        <BaseCard title="异常类型分布">
          <dl class="distribution-list">
            <div v-for="item in entries(report.metrics.exception_dist, ERROR_TYPE_LABEL)" :key="item.key">
              <dt>{{ item.label }}</dt><dd>{{ item.value }}</dd>
            </div>
          </dl>
        </BaseCard>
        <BaseCard title="Agent 决策分布">
          <dl class="distribution-list">
            <div v-for="item in entries(report.metrics.agent_decision_dist)" :key="item.key">
              <dt>{{ item.label }}</dt><dd>{{ item.value }}</dd>
            </div>
          </dl>
        </BaseCard>
        <BaseCard title="Fallback 分布">
          <dl class="distribution-list">
            <div v-for="item in entries(report.metrics.fallback_dist)" :key="item.key">
              <dt>{{ item.label }}</dt><dd>{{ item.value }}</dd>
            </div>
          </dl>
        </BaseCard>
        <BaseCard title="RAG 引用">
          <ul v-if="report.metrics.rag_sources.length" class="source-list">
            <li v-for="source in report.metrics.rag_sources" :key="source">{{ source }}</li>
          </ul>
          <EmptyState v-else title="暂无引用" description="本任务未记录 RAG 引用来源。" />
        </BaseCard>
      </div>

      <section class="narrative-panel" aria-labelledby="narrative-title">
        <header>
          <span>REPORT NARRATIVE</span>
          <h2 id="narrative-title">审计叙述</h2>
        </header>
        <article>
          <h3>高风险事项</h3>
          <p>{{ report.narrative.risk_summary }}</p>
        </article>
        <article>
          <h3>人工复核建议</h3>
          <p>{{ report.narrative.review_advice }}</p>
        </article>
        <article>
          <h3>后续建议</h3>
          <p>{{ report.narrative.followup }}</p>
        </article>
      </section>
    </template>

    <EmptyState
      v-else-if="!loading"
      title="等待生成审计报告"
      description="输入已完成或处理中任务的编号，系统将聚合最新数据并生成报告。"
    />
  </div>
</template>

<style scoped>
.report-page {
  display: grid;
  gap: var(--space-8);
}

.report-form {
  display: grid;
  gap: var(--space-3);
}

.report-form label {
  color: var(--color-text);
  font-size: 14px;
  font-weight: 600;
}

.report-form__controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--space-3);
}

.report-form input {
  min-width: 0;
  padding: 0 var(--space-4);
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
  font-size: 14px;
  outline: none;
  transition: border-color var(--duration-fast) var(--ease-standard),
    box-shadow var(--duration-fast) var(--ease-standard);
}

.report-form input:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-soft);
}

.report-form p,
.report-page__feedback {
  margin: 0;
  color: var(--color-text-subtle);
  font-size: 13px;
}

.report-page__error {
  padding: var(--space-4) var(--space-5);
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, var(--color-surface));
  border: 1px solid color-mix(in srgb, var(--color-danger) 28%, var(--color-border-soft));
  border-radius: var(--radius-md);
}

.report-meta {
  display: grid;
  grid-template-columns: 1fr 1.4fr 1fr auto;
  gap: var(--space-4);
  align-items: center;
  padding: var(--space-4) var(--space-5);
  background: var(--color-surface-muted);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-lg);
}

.report-meta > div:not(.report-meta__actions) {
  display: grid;
  gap: var(--space-1);
}

.report-meta span {
  color: var(--color-text-subtle);
  font-size: 12px;
}

.report-meta strong {
  overflow-wrap: anywhere;
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 500;
}

.report-meta__actions {
  display: flex;
  gap: var(--space-2);
}

.report-section {
  display: grid;
  gap: var(--space-4);
}

.report-section h2 {
  margin: 0;
  color: var(--color-text);
  font-size: 18px;
}

.report-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
}

.report-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

.distribution-list {
  display: grid;
  gap: var(--space-3);
  margin: 0;
}

.distribution-list div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-4);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--color-border-soft);
}

.distribution-list div:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.distribution-list dt,
.distribution-list dd {
  margin: 0;
  font-size: 14px;
}

.distribution-list dt {
  color: var(--color-text-muted);
}

.distribution-list dd {
  color: var(--color-text);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-weight: 650;
}

.source-list {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding-left: var(--space-5);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.narrative-panel {
  display: grid;
  grid-template-columns: 0.7fr repeat(3, 1fr);
  gap: 0;
  overflow: hidden;
  background: var(--color-surface);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
}

.narrative-panel header,
.narrative-panel article {
  padding: var(--space-6);
}

.narrative-panel header {
  background: var(--color-surface-muted);
}

.narrative-panel article {
  border-left: 1px solid var(--color-border-soft);
}

.narrative-panel span {
  color: var(--color-accent);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
}

.narrative-panel h2,
.narrative-panel h3,
.narrative-panel p {
  margin: 0;
}

.narrative-panel h2 {
  margin-top: var(--space-2);
  font-family: var(--font-serif);
  font-size: 22px;
  font-weight: 500;
}

.narrative-panel h3 {
  color: var(--color-text);
  font-size: 14px;
  font-weight: 600;
}

.narrative-panel p {
  margin-top: var(--space-3);
  color: var(--color-text-muted);
  font-family: var(--font-serif);
  font-size: 15px;
  line-height: 1.75;
}

@media (max-width: 980px) {
  .report-meta,
  .narrative-panel {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .narrative-panel article:nth-of-type(2) {
    border-left: 0;
  }
}

@media (max-width: 680px) {
  .report-form__controls,
  .report-meta,
  .report-stats,
  .report-grid,
  .narrative-panel {
    grid-template-columns: 1fr;
  }

  .report-form input {
    min-height: 40px;
  }

  .report-meta__actions {
    flex-wrap: wrap;
  }

  .narrative-panel article {
    border-top: 1px solid var(--color-border-soft);
    border-left: 0;
  }
}
</style>
