<script setup lang="ts">
import type { PendingReviewItem, ReviewAction } from "../../types/api";
import { ERROR_TYPE_LABEL, STATUS_META } from "../../constants/enums";
import BaseButton from "../ui/BaseButton.vue";
import BaseCard from "../ui/BaseCard.vue";
import RiskBadge from "../ui/RiskBadge.vue";

const props = defineProps<{
  item: PendingReviewItem;
}>();

const emit = defineEmits<{
  action: [item: PendingReviewItem, action: ReviewAction];
}>();

function confidenceText(value: number | null) {
  if (value === null) {
    return "—";
  }
  return `${Math.round(value * 100)}%`;
}

function scoreText(value: number | null) {
  if (value === null) {
    return "—";
  }
  return value.toFixed(3);
}

function statusLabel(value: string) {
  return STATUS_META[value]?.label ?? value;
}

function amountText(value: string | null) {
  if (value === null) {
    return "无对应流水";
  }
  return value;
}

function serialText(value: string | null) {
  if (value === null) {
    return "无对应流水";
  }
  return value;
}
</script>

<template>
  <BaseCard>
    <template #header>
      <div class="review-card__header">
        <div>
          <p class="review-card__eyebrow">
            流水 #{{ item.flow_id }}
          </p>
          <h2>{{ ERROR_TYPE_LABEL[item.error_type] ?? item.error_type }}</h2>
        </div>
        <RiskBadge :level="item.risk_level" />
      </div>
    </template>

    <div class="review-card">
      <dl class="review-card__identifiers">
        <div>
          <dt>任务</dt>
          <dd class="cell-mono">{{ item.task_id }}</dd>
        </div>
        <div>
          <dt>队列</dt>
          <dd class="cell-mono">{{ item.queue_id }}</dd>
        </div>
      </dl>

      <section class="review-card__section">
        <h3>流水信息</h3>
        <dl class="review-card__amounts">
          <div>
            <dt>银行流水号</dt>
            <dd class="cell-mono">{{ serialText(item.bank_serial_no) }}</dd>
          </div>
          <div>
            <dt>清算流水号</dt>
            <dd class="cell-mono">{{ serialText(item.clearing_serial_no) }}</dd>
          </div>
          <div>
            <dt>银行金额</dt>
            <dd class="cell-mono">{{ amountText(item.bank_amount) }}</dd>
          </div>
          <div>
            <dt>清算金额</dt>
            <dd class="cell-mono">{{ amountText(item.clear_amount) }}</dd>
          </div>
          <div>
            <dt>差额</dt>
            <dd class="cell-mono">{{ item.discrepancy_amount }}</dd>
          </div>
        </dl>
      </section>

      <dl class="review-card__meta">
        <div>
          <dt>规则分支</dt>
          <dd class="cell-mono">{{ item.exception_branch ?? "—" }}</dd>
        </div>
        <div>
          <dt>处理状态</dt>
          <dd>{{ statusLabel(item.ai_suggestion) }}</dd>
        </div>
        <div>
          <dt>AI 置信度</dt>
          <dd class="cell-mono">{{ confidenceText(item.ai_confidence) }}</dd>
        </div>
      </dl>

      <section class="review-card__section">
        <h3>AI 理由</h3>
        <p>{{ item.ai_reason ?? "—" }}</p>
      </section>

      <section class="review-card__section">
        <h3>RAG 来源</h3>
        <ul v-if="item.rag_sources.length" class="review-card__sources">
          <li v-for="source in item.rag_sources" :key="`${source.source}-${source.score}`">
            <span>{{ source.source }}</span>
            <strong class="cell-mono">{{ scoreText(source.score) }}</strong>
          </li>
        </ul>
        <p v-else>—</p>
      </section>
    </div>

    <template #footer>
      <div class="review-card__actions">
        <BaseButton variant="secondary" @click="emit('action', props.item, 'FORCE_HOLD')">
          强制挂账
        </BaseButton>
        <BaseButton @click="emit('action', props.item, 'APPROVED_MATCH')">
          确认平账
        </BaseButton>
      </div>
    </template>
  </BaseCard>
</template>

<style scoped>
.review-card__header {
  display: flex;
  gap: var(--space-4);
  align-items: flex-start;
  justify-content: space-between;
}

.review-card__eyebrow {
  margin: 0 0 var(--space-2);
  color: var(--color-text-subtle);
  font-size: 12px;
  font-weight: 600;
}

h2,
h3 {
  margin: 0;
  color: var(--color-text);
  font-weight: 600;
}

h2 {
  font-size: 16px;
}

h3 {
  font-size: 14px;
}

.review-card {
  display: grid;
  gap: var(--space-5);
}

.review-card__identifiers {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
  margin: 0;
}

.review-card__identifiers div {
  min-width: 0;
  padding: var(--space-3);
  background: var(--color-bg-soft);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
}

.review-card__meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-3);
  margin: 0;
}

.review-card__meta div {
  min-width: 0;
  padding: var(--space-3);
  background: var(--color-bg-soft);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
}

.review-card__amounts {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--space-3);
  margin: 0;
}

.review-card__amounts div {
  min-width: 0;
  padding: var(--space-3);
  background: var(--color-bg-soft);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
}

dt {
  margin: 0 0 var(--space-1);
  color: var(--color-text-muted);
  font-size: 12px;
  line-height: 1.5;
}

dd,
.review-card__section p {
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--color-text);
  font-size: 14px;
  line-height: 1.7;
}

.review-card__section {
  display: grid;
  gap: var(--space-2);
}

.review-card__sources {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.review-card__sources li {
  display: flex;
  gap: var(--space-3);
  align-items: baseline;
  justify-content: space-between;
  padding: var(--space-3);
  background: var(--color-bg-soft);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
}

.review-card__sources span {
  overflow-wrap: anywhere;
  color: var(--color-text);
  font-size: 13px;
  line-height: 1.5;
}

.review-card__sources strong {
  color: var(--color-text-muted);
  font-size: 12px;
}

.review-card__actions {
  display: flex;
  gap: var(--space-3);
  justify-content: flex-end;
}

@media (max-width: 1000px) {
  .review-card__amounts {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .review-card__meta,
  .review-card__identifiers {
    grid-template-columns: 1fr;
  }

  .review-card__amounts {
    grid-template-columns: 1fr;
  }

  .review-card__actions {
    flex-direction: column-reverse;
  }
}
</style>
