<script setup lang="ts">
import { computed } from "vue";

import type { AgentStreamEvent } from "../../types/api";
import RiskBadge from "../ui/RiskBadge.vue";
import StatusBadge from "../ui/StatusBadge.vue";

const props = defineProps<{ event: AgentStreamEvent }>();

const EVENT_LABEL: Record<AgentStreamEvent["event_type"], string> = {
  task_started: "任务启动",
  task_progress: "任务进度",
  hook: "Hook 校验",
  rag_retrieved: "RAG 召回",
  agent_decision: "Agent 决策",
  fallback: "Fallback",
  item_done: "单项完成",
  task_done: "任务完成",
};

const payload = computed(() => props.event.payload);
const payloadValue = computed(() => payload.value as Record<string, unknown>);
const formattedTime = computed(() => {
  const date = new Date(props.event.ts);
  if (Number.isNaN(date.getTime())) {
    return props.event.ts;
  }
  return date.toLocaleTimeString("zh-CN", { hour12: false });
});

const confidenceText = computed(() => {
  const confidence = payloadValue.value.confidence;
  if (typeof confidence !== "number") {
    return "";
  }
  return `${Math.round(confidence * 100)}%`;
});

const ragScoreText = computed(() => {
  const score = payloadValue.value.best_score;
  if (typeof score !== "number") {
    return "";
  }
  return score.toFixed(2);
});

function stringField(key: string): string {
  const value = payloadValue.value[key];
  return typeof value === "string" ? value : "";
}

function numberField(key: string): number | null {
  const value = payloadValue.value[key];
  return typeof value === "number" ? value : null;
}

const chunkIds = computed(() => {
  const value = payloadValue.value.chunk_ids;
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
});
</script>

<template>
  <article class="event-card" :class="`event-card--${event.event_type}`">
    <header class="event-card__header">
      <div>
        <p class="event-card__label">{{ EVENT_LABEL[event.event_type] }}</p>
        <p class="event-card__meta">#{{ event.seq }} · {{ formattedTime }}</p>
      </div>
      <StatusBadge v-if="stringField('status')" :value="stringField('status')" />
      <span v-else-if="event.flow_id" class="event-card__flow">{{ event.flow_id }}</span>
    </header>

    <dl class="event-card__details">
      <div v-if="stringField('scenario_type')">
        <dt>场景</dt>
        <dd>{{ stringField("scenario_type") }}</dd>
      </div>
      <div v-if="stringField('agent_name')">
        <dt>Agent</dt>
        <dd>{{ stringField("agent_name") }}</dd>
      </div>
      <div v-if="stringField('hook_name')">
        <dt>Hook</dt>
        <dd>{{ stringField("hook_name") }}</dd>
      </div>
      <div v-if="stringField('query')">
        <dt>检索问题</dt>
        <dd>{{ stringField("query") }}</dd>
      </div>
      <div v-if="ragScoreText">
        <dt>最佳分数</dt>
        <dd>{{ ragScoreText }}</dd>
      </div>
      <div v-if="chunkIds.length">
        <dt>规则片段</dt>
        <dd>{{ chunkIds.join("、") }}</dd>
      </div>
      <div v-if="stringField('decision')">
        <dt>决策</dt>
        <dd>{{ stringField("decision") }}</dd>
      </div>
      <div v-if="confidenceText">
        <dt>置信度</dt>
        <dd>{{ confidenceText }}</dd>
      </div>
      <div v-if="numberField('fallback_level') !== null">
        <dt>Fallback 层级</dt>
        <dd>L{{ numberField("fallback_level") }}</dd>
      </div>
      <div v-if="stringField('reason')">
        <dt>原因</dt>
        <dd>{{ stringField("reason") }}</dd>
      </div>
      <div v-if="stringField('next_action')">
        <dt>下一步</dt>
        <dd>{{ stringField("next_action") }}</dd>
      </div>
      <div v-if="stringField('risk_level')">
        <dt>风险</dt>
        <dd><RiskBadge :level="stringField('risk_level')" /></dd>
      </div>
    </dl>
  </article>
</template>

<style scoped>
.event-card {
  position: relative;
  padding: var(--space-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-soft);
}

.event-card::before {
  position: absolute;
  top: var(--space-4);
  left: calc(var(--space-4) * -1 - 5px);
  width: 10px;
  height: 10px;
  background: var(--color-surface);
  border: 2px solid var(--color-info);
  border-radius: var(--radius-full);
  content: "";
}

.event-card--task_done::before {
  border-color: var(--color-success);
}

.event-card--fallback::before {
  border-color: var(--color-warning);
}

.event-card__header {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  justify-content: space-between;
}

.event-card__label,
.event-card__meta,
.event-card__details,
.event-card__details dd {
  margin: 0;
}

.event-card__label {
  color: var(--color-text);
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
}

.event-card__meta,
.event-card__flow,
.event-card__details dt {
  color: var(--color-text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.event-card__flow {
  font-family: var(--font-mono);
}

.event-card__details {
  display: grid;
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.event-card__details div {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: var(--space-3);
}

.event-card__details dd {
  min-width: 0;
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

@media (max-width: 640px) {
  .event-card__details div {
    grid-template-columns: 1fr;
    gap: var(--space-1);
  }
}
</style>
