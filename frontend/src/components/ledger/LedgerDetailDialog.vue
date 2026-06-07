<script setup lang="ts">
import { computed } from "vue";
import type { LedgerRow } from "../../types/api";
import { ERROR_TYPE_LABEL } from "../../constants/enums";
import StatusBadge from "../ui/StatusBadge.vue";

const props = defineProps<{
  modelValue: boolean;
  row: LedgerRow | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});

const ragSources = computed(() => {
  if (!props.row?.rag_source) {
    return [];
  }
  return props.row.rag_source
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
});

function valueOrDash(value: string | number | null) {
  return value === null || value === "" ? "—" : String(value);
}
</script>

<template>
  <ElDialog v-model="visible" title="差错详情" width="720px" destroy-on-close>
    <div v-if="row" class="ledger-detail">
      <section class="ledger-detail__section">
        <h3>基本信息</h3>
        <dl class="ledger-detail__grid">
          <div>
            <dt>ID</dt>
            <dd class="cell-mono">{{ row.id }}</dd>
          </div>
          <div>
            <dt>任务 ID</dt>
            <dd class="cell-mono">{{ row.task_id }}</dd>
          </div>
          <div>
            <dt>流水号</dt>
            <dd class="cell-mono">{{ row.flow_id }}</dd>
          </div>
          <div>
            <dt>异常类型</dt>
            <dd>{{ ERROR_TYPE_LABEL[row.error_type] ?? row.error_type }}</dd>
          </div>
          <div>
            <dt>规则分支</dt>
            <dd class="cell-mono">{{ valueOrDash(row.exception_branch) }}</dd>
          </div>
          <div>
            <dt>处理状态</dt>
            <dd><StatusBadge :value="row.handle_status" /></dd>
          </div>
          <div>
            <dt>银行端金额</dt>
            <dd class="cell-mono amount">{{ valueOrDash(row.bank_amount) }}</dd>
          </div>
          <div>
            <dt>企业/清算端金额</dt>
            <dd class="cell-mono amount">{{ valueOrDash(row.clear_amount) }}</dd>
          </div>
          <div>
            <dt>差异金额</dt>
            <dd class="cell-mono amount">{{ valueOrDash(row.discrepancy_amount) }}</dd>
          </div>
          <div>
            <dt>AI 置信度</dt>
            <dd class="cell-mono">{{ valueOrDash(row.ai_confidence) }}</dd>
          </div>
        </dl>
      </section>

      <section class="ledger-detail__section">
        <h3>AI 审计意见</h3>
        <p class="ledger-detail__body">{{ valueOrDash(row.ai_audit_opinion) }}</p>
      </section>

      <section class="ledger-detail__section">
        <h3>RAG 来源</h3>
        <ul v-if="ragSources.length" class="ledger-detail__sources">
          <li v-for="source in ragSources" :key="source">{{ source }}</li>
        </ul>
        <p v-else class="ledger-detail__body">—</p>
      </section>

      <p class="ledger-detail__note">该接口未返回处理人/备注。</p>
    </div>
  </ElDialog>
</template>

<style scoped>
.ledger-detail {
  display: grid;
  gap: var(--space-6);
}

.ledger-detail__section {
  display: grid;
  gap: var(--space-3);
}

h3 {
  margin: 0;
  color: var(--color-text);
  font-size: 15px;
  font-weight: 600;
}

.ledger-detail__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
  margin: 0;
}

.ledger-detail__grid div {
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

dd {
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--color-text);
  font-size: 14px;
  line-height: 1.5;
}

.amount {
  text-align: right;
}

.ledger-detail__body,
.ledger-detail__note {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 14px;
  line-height: 1.7;
}

.ledger-detail__sources {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.ledger-detail__sources li {
  padding: var(--space-3);
  overflow-wrap: anywhere;
  color: var(--color-text);
  background: var(--color-bg-soft);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.5;
}

.ledger-detail__note {
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-border-soft);
}

@media (max-width: 640px) {
  .ledger-detail__grid {
    grid-template-columns: 1fr;
  }
}
</style>
