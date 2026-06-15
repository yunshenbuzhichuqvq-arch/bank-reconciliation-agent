<script setup lang="ts">
import { computed, ref } from "vue";

import { useReconcileStream } from "../composables/useReconcileStream";
import type { TaskDonePayload } from "../types/api";
import { SCENARIO_META, type ScenarioType } from "../constants/enums";
import EventTimeline from "../components/workbench/EventTimeline.vue";
import FilePicker from "../components/upload/FilePicker.vue";
import BaseButton from "../components/ui/BaseButton.vue";
import BaseCard from "../components/ui/BaseCard.vue";
import PageHeader from "../components/ui/PageHeader.vue";

const stream = useReconcileStream();

const scenario = ref<ScenarioType>("BANK_ENTERPRISE");
const scenarioEntries = Object.entries(SCENARIO_META) as [ScenarioType, typeof SCENARIO_META[ScenarioType]][];
const bankFile = ref<File | null>(null);
const clearFile = ref<File | null>(null);

const isStreaming = computed(() => stream.status.value === "streaming");
const canStart = computed(() => Boolean(bankFile.value && clearFile.value && !isStreaming.value));
const taskDone = computed(() => {
  const result = stream.result.value;
  const resultRecord = result as Record<string, unknown> | null;
  if (!resultRecord || typeof resultRecord.status !== "string") {
    return null;
  }
  return result as TaskDonePayload;
});

const summaryStats = computed(() => {
  if (!taskDone.value) {
    return [];
  }
  return [
    { label: "银行端流水", value: taskDone.value.total_bank_rows },
    { label: "企业/清算端流水", value: taskDone.value.total_clear_rows },
    { label: "自动修复", value: taskDone.value.auto_fixed_rows },
    { label: "待 AI 审核", value: taskDone.value.pending_ai_rows },
    { label: "待人工复核", value: taskDone.value.pending_human_rows },
  ].filter((item) => typeof item.value === "number");
});

async function startStream() {
  if (!bankFile.value || !clearFile.value || isStreaming.value) {
    return;
  }

  await stream.start({
    bankFile: bankFile.value,
    clearFile: clearFile.value,
    scenarioType: scenario.value,
  });
}
</script>

<template>
  <PageHeader
    title="Agent 流式工作台"
    description="上传银行端与企业/清算端流水，实时观察 Hook、RAG、Agent 决策与 Fallback 事件。"
  />

  <div class="workbench-page">
    <BaseCard title="流式审计输入">
      <div class="workbench-page__scenario">
        <p>场景</p>
        <div class="workbench-page__scenario-options" role="radiogroup" aria-label="对账场景">
          <label v-for="[value, meta] in scenarioEntries" :key="value">
            <input v-model="scenario" type="radio" :value="value">
            <span>
              <strong>{{ meta.label }}</strong>
              <small>{{ meta.description }}</small>
            </span>
          </label>
        </div>
      </div>

      <div class="workbench-page__files">
        <FilePicker
          v-model="bankFile"
          input-id="workbench-bank-file"
          label="银行端流水"
          description="对应 multipart 字段 bank_file。支持 .xlsx / .xls。"
        />
        <FilePicker
          v-model="clearFile"
          input-id="workbench-clear-file"
          label="企业/清算端流水"
          description="对应 multipart 字段 clear_file。支持 .xlsx / .xls。"
        />
      </div>

      <template #footer>
        <div class="workbench-page__actions">
          <p>{{ isStreaming ? "流正在接收事件，可随时中止。" : "两份文件齐全后即可启动流式审计。" }}</p>
          <div>
            <BaseButton
              v-if="isStreaming"
              variant="secondary"
              @click="stream.abort"
            >
              中止
            </BaseButton>
            <BaseButton
              :disabled="!canStart"
              :loading="isStreaming"
              @click="startStream"
            >
              启动流式审计
            </BaseButton>
          </div>
        </div>
      </template>
    </BaseCard>

    <div v-if="stream.error.value" class="workbench-page__error" role="alert">
      <strong>流式审计失败</strong>
      <span>{{ stream.error.value }}</span>
    </div>

    <BaseCard title="事件时间线">
      <EventTimeline :events="stream.events.value" />
    </BaseCard>

    <BaseCard v-if="taskDone" title="终态计数">
      <div class="workbench-page__result">
        <div class="workbench-page__result-status">
          <p>任务状态</p>
          <strong>{{ taskDone.status }}</strong>
        </div>
        <dl class="workbench-page__stats">
          <div v-for="item in summaryStats" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd>{{ item.value }}</dd>
          </div>
        </dl>
      </div>
    </BaseCard>
  </div>
</template>

<style scoped>
.workbench-page {
  display: grid;
  gap: var(--space-6);
}

.workbench-page__scenario {
  display: grid;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}

.workbench-page__scenario-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.workbench-page__scenario > p,
.workbench-page__actions p,
.workbench-page__result-status p,
.workbench-page__stats dt {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.workbench-page__scenario label {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  min-width: 0;
  padding: var(--space-4);
  background: var(--color-bg-soft);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition:
    border-color var(--duration-fast) var(--ease-standard),
    background-color var(--duration-fast) var(--ease-standard);
}

.workbench-page__scenario label:has(input:checked) {
  background: color-mix(in srgb, var(--color-accent-soft) 42%, var(--color-surface));
  border-color: color-mix(in srgb, var(--color-accent) 42%, var(--color-border-soft));
}

.workbench-page__scenario input {
  width: 16px;
  height: 16px;
  margin: 3px 0 0;
  accent-color: var(--color-text);
}

.workbench-page__scenario span {
  display: grid;
  gap: var(--space-1);
}

.workbench-page__scenario strong {
  color: var(--color-text);
  font-size: 15px;
  font-weight: 600;
}

.workbench-page__scenario small {
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.workbench-page__files {
  display: grid;
  gap: var(--space-4);
}

.workbench-page__actions,
.workbench-page__actions div {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}

.workbench-page__actions {
  justify-content: space-between;
}

.workbench-page__error {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-5);
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, var(--color-surface));
  border: 1px solid color-mix(in srgb, var(--color-danger) 28%, var(--color-border-soft));
  border-radius: var(--radius-md);
}

.workbench-page__error strong,
.workbench-page__error span {
  font-size: 14px;
  line-height: 1.5;
}

.workbench-page__error span {
  font-family: var(--font-mono);
}

.workbench-page__result {
  display: grid;
  gap: var(--space-5);
}

.workbench-page__result-status {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--color-border-soft);
}

.workbench-page__result-status strong {
  color: var(--color-success);
  font-family: var(--font-mono);
  font-size: 14px;
}

.workbench-page__stats {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--space-3);
  margin: 0;
}

.workbench-page__stats div {
  min-width: 0;
  padding: var(--space-4);
  background: var(--color-bg-soft);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
}

.workbench-page__stats dd {
  margin: var(--space-2) 0 0;
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: 22px;
  font-variant-numeric: tabular-nums;
  font-weight: 650;
  line-height: 1.2;
}

@media (max-width: 820px) {
  .workbench-page__scenario-options {
    grid-template-columns: 1fr;
  }

  .workbench-page__actions {
    align-items: stretch;
    flex-direction: column;
  }

  .workbench-page__actions div {
    justify-content: flex-end;
  }

  .workbench-page__stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
