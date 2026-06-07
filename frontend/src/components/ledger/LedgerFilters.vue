<script setup lang="ts">
import { computed } from "vue";
import BaseButton from "../ui/BaseButton.vue";
import { ERROR_TYPE_LABEL, STATUS_META } from "../../constants/enums";

export interface LedgerFilterModel {
  task_id: string;
  error_type: string;
  handle_status: string;
  start_date: string;
  end_date: string;
}

const props = defineProps<{
  modelValue: LedgerFilterModel;
  loading?: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: LedgerFilterModel];
  submit: [];
  reset: [];
}>();

const errorTypeOptions = [
  "AMOUNT_MISMATCH",
  "NARRATIVE_NAME_MISMATCH",
  "BANK_UNARRIVED",
  "BOOK_UNRECORDED",
  "DUPLICATE_BOOKING",
];

const handleStatusOptions = ["PENDING_HUMAN", "FIXED", "HELD", "AUTO_FIXED"];

const filters = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});

function patch<K extends keyof LedgerFilterModel>(key: K, value: LedgerFilterModel[K]) {
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}
</script>

<template>
  <section class="ledger-filters" aria-label="台账筛选">
    <label class="ledger-filters__field">
      <span>任务 ID</span>
      <ElInput
        :model-value="filters.task_id"
        placeholder="输入 task_id"
        clearable
        @update:model-value="patch('task_id', String($event))"
        @keyup.enter="emit('submit')"
      />
    </label>

    <label class="ledger-filters__field">
      <span>异常类型</span>
      <ElSelect
        :model-value="filters.error_type"
        placeholder="全部"
        clearable
        @update:model-value="patch('error_type', String($event ?? ''))"
      >
        <ElOption label="全部" value="" />
        <ElOption
          v-for="item in errorTypeOptions"
          :key="item"
          :label="ERROR_TYPE_LABEL[item]"
          :value="item"
        />
      </ElSelect>
    </label>

    <label class="ledger-filters__field">
      <span>处理状态</span>
      <ElSelect
        :model-value="filters.handle_status"
        placeholder="全部"
        clearable
        @update:model-value="patch('handle_status', String($event ?? ''))"
      >
        <ElOption label="全部" value="" />
        <ElOption
          v-for="item in handleStatusOptions"
          :key="item"
          :label="STATUS_META[item]?.label ?? item"
          :value="item"
        />
      </ElSelect>
    </label>

    <label class="ledger-filters__field">
      <span>开始日期</span>
      <ElInput
        :model-value="filters.start_date"
        placeholder="YYYY-MM-DD"
        clearable
        @update:model-value="patch('start_date', String($event))"
        @keyup.enter="emit('submit')"
      />
    </label>

    <label class="ledger-filters__field">
      <span>结束日期</span>
      <ElInput
        :model-value="filters.end_date"
        placeholder="YYYY-MM-DD"
        clearable
        @update:model-value="patch('end_date', String($event))"
        @keyup.enter="emit('submit')"
      />
    </label>

    <div class="ledger-filters__actions">
      <BaseButton variant="secondary" :disabled="loading" @click="emit('reset')">重置</BaseButton>
      <BaseButton :loading="loading" @click="emit('submit')">查询</BaseButton>
    </div>
  </section>
</template>

<style scoped>
.ledger-filters {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
  padding: var(--space-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
}

.ledger-filters__field {
  display: grid;
  gap: var(--space-2);
}

.ledger-filters__field span {
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.ledger-filters__actions {
  display: flex;
  gap: var(--space-2);
  align-items: end;
  justify-content: flex-end;
}

@media (max-width: 980px) {
  .ledger-filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .ledger-filters {
    grid-template-columns: 1fr;
  }

  .ledger-filters__actions {
    justify-content: stretch;
  }
}
</style>
