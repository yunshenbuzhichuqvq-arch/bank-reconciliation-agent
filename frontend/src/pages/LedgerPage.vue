<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { listLedger } from "../api/ledger";
import type { ApiError } from "../api/client";
import type { LedgerRow } from "../types/api";
import { ERROR_TYPE_LABEL } from "../constants/enums";
import LedgerDetailDialog from "../components/ledger/LedgerDetailDialog.vue";
import LedgerFilters, { type LedgerFilterModel } from "../components/ledger/LedgerFilters.vue";
import BaseCard from "../components/ui/BaseCard.vue";
import EmptyState from "../components/ui/EmptyState.vue";
import PageHeader from "../components/ui/PageHeader.vue";
import StatusBadge from "../components/ui/StatusBadge.vue";

const query = reactive<LedgerFilterModel & { page: number; page_size: number }>({
  task_id: "",
  error_type: "",
  handle_status: "",
  start_date: "",
  end_date: "",
  page: 1,
  page_size: 20,
});

const rows = ref<LedgerRow[]>([]);
const total = ref(0);
const loading = ref(false);
const errorText = ref("");
const selectedRow = ref<LedgerRow | null>(null);
const detailVisible = ref(false);

const filters = computed({
  get: () => ({
    task_id: query.task_id,
    error_type: query.error_type,
    handle_status: query.handle_status,
    start_date: query.start_date,
    end_date: query.end_date,
  }),
  set: (value: LedgerFilterModel) => {
    query.task_id = value.task_id;
    query.error_type = value.error_type;
    query.handle_status = value.handle_status;
    query.start_date = value.start_date;
    query.end_date = value.end_date;
  },
});

onMounted(() => {
  fetchLedger();
});

async function fetchLedger() {
  loading.value = true;
  errorText.value = "";

  try {
    const data = await listLedger(buildParams());
    rows.value = data.items;
    total.value = data.total;
    query.page = data.page;
    query.page_size = data.page_size;
  } catch (error) {
    errorText.value = (error as ApiError).message ?? "台账查询失败";
    rows.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}

function buildParams() {
  return {
    task_id: optional(query.task_id),
    error_type: optional(query.error_type),
    handle_status: optional(query.handle_status),
    start_date: optional(query.start_date),
    end_date: optional(query.end_date),
    page: query.page,
    page_size: query.page_size,
  };
}

function optional(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function submitFilters() {
  query.page = 1;
  fetchLedger();
}

function resetFilters() {
  query.task_id = "";
  query.error_type = "";
  query.handle_status = "";
  query.start_date = "";
  query.end_date = "";
  query.page = 1;
  fetchLedger();
}

function onPageChange(page: number) {
  query.page = page;
  fetchLedger();
}

function onPageSizeChange(pageSize: number) {
  query.page_size = pageSize;
  query.page = 1;
  fetchLedger();
}

function openDetail(row: LedgerRow) {
  selectedRow.value = row;
  detailVisible.value = true;
}

function valueOrDash(value: string | number | null) {
  return value === null || value === "" ? "—" : String(value);
}
</script>

<template>
  <PageHeader
    title="差错台账"
    description="按任务、异常类型、处理状态和日期范围查询差错记录。"
  />

  <div class="ledger-page">
    <LedgerFilters
      v-model="filters"
      :loading="loading"
      @submit="submitFilters"
      @reset="resetFilters"
    />

    <div v-if="errorText" class="ledger-page__error" role="alert">
      <strong>查询失败</strong>
      <span>{{ errorText }}</span>
    </div>

    <BaseCard>
      <ElTable
        v-loading="loading"
        :data="rows"
        row-key="id"
        class="ledger-table"
        @row-click="openDetail"
      >
        <ElTableColumn prop="flow_id" label="流水号" min-width="150" class-name="cell-mono" />
        <ElTableColumn label="异常类型" min-width="150">
          <template #default="{ row }">
            {{ ERROR_TYPE_LABEL[row.error_type] ?? row.error_type }}
          </template>
        </ElTableColumn>
        <ElTableColumn
          prop="exception_branch"
          label="规则分支"
          min-width="110"
          class-name="cell-mono"
        >
          <template #default="{ row }">
            {{ valueOrDash(row.exception_branch) }}
          </template>
        </ElTableColumn>
        <ElTableColumn
          prop="bank_amount"
          label="银行端金额"
          min-width="130"
          align="right"
          class-name="cell-mono"
        >
          <template #default="{ row }">
            {{ valueOrDash(row.bank_amount) }}
          </template>
        </ElTableColumn>
        <ElTableColumn
          prop="clear_amount"
          label="企业端金额"
          min-width="130"
          align="right"
          class-name="cell-mono"
        >
          <template #default="{ row }">
            {{ valueOrDash(row.clear_amount) }}
          </template>
        </ElTableColumn>
        <ElTableColumn
          prop="discrepancy_amount"
          label="差异金额"
          min-width="130"
          align="right"
          class-name="cell-mono"
        >
          <template #default="{ row }">
            {{ valueOrDash(row.discrepancy_amount) }}
          </template>
        </ElTableColumn>
        <ElTableColumn
          prop="ai_confidence"
          label="AI 置信度"
          min-width="110"
          class-name="cell-mono"
        >
          <template #default="{ row }">
            {{ valueOrDash(row.ai_confidence) }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="处理状态" min-width="120">
          <template #default="{ row }">
            <StatusBadge :value="row.handle_status" />
          </template>
        </ElTableColumn>
        <template #empty>
          <span class="ledger-table__empty" />
        </template>
      </ElTable>

      <EmptyState
        v-if="!loading && total === 0"
        title="未找到匹配的差错记录"
        description="请调整筛选条件后重新查询。"
      />

      <template #footer>
        <div class="ledger-page__pagination">
          <span>共 {{ total }} 条</span>
          <ElPagination
            background
            layout="sizes, prev, pager, next"
            :current-page="query.page"
            :page-size="query.page_size"
            :page-sizes="[10, 20, 50]"
            :total="total"
            @current-change="onPageChange"
            @size-change="onPageSizeChange"
          />
        </div>
      </template>
    </BaseCard>

    <LedgerDetailDialog v-model="detailVisible" :row="selectedRow" />
  </div>
</template>

<style scoped>
.ledger-page {
  display: grid;
  gap: var(--space-6);
}

.ledger-page__error {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-5);
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, var(--color-surface));
  border: 1px solid color-mix(in srgb, var(--color-danger) 28%, var(--color-border-soft));
  border-radius: var(--radius-md);
}

.ledger-page__error strong,
.ledger-page__error span {
  font-size: 14px;
  line-height: 1.5;
}

.ledger-page__error span {
  font-family: var(--font-mono);
}

.ledger-table {
  width: 100%;
  cursor: pointer;
}

.ledger-table__empty {
  display: block;
  min-height: var(--space-6);
}

.ledger-page__pagination {
  display: flex;
  gap: var(--space-4);
  align-items: center;
  justify-content: space-between;
}

.ledger-page__pagination span {
  color: var(--color-text-muted);
  font-size: 13px;
}

@media (max-width: 760px) {
  .ledger-page__pagination {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
