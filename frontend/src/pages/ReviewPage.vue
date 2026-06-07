<script setup lang="ts">
import { ElMessage } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";
import { approveReview, listPending } from "../api/review";
import type { ApiError } from "../api/client";
import type { PendingReviewItem, ReviewAction, ReviewResult } from "../types/api";
import { STATUS_META } from "../constants/enums";
import ApproveDialog from "../components/review/ApproveDialog.vue";
import ReviewCard from "../components/review/ReviewCard.vue";
import BaseButton from "../components/ui/BaseButton.vue";
import BaseCard from "../components/ui/BaseCard.vue";
import EmptyState from "../components/ui/EmptyState.vue";
import PageHeader from "../components/ui/PageHeader.vue";

const handlerStorageKey = "mvp1-review-handler";

const query = reactive({
  task_id: "",
  page: 1,
  page_size: 10,
});

const items = ref<PendingReviewItem[]>([]);
const total = ref(0);
const loading = ref(false);
const submitting = ref(false);
const errorText = ref("");
const selectedItem = ref<PendingReviewItem | null>(null);
const selectedAction = ref<ReviewAction | null>(null);
const dialogVisible = ref(false);
const lastHandler = ref(localStorage.getItem(handlerStorageKey) || "reviewer");

const hasItems = computed(() => items.value.length > 0);

onMounted(() => {
  fetchPending();
});

async function fetchPending() {
  loading.value = true;
  errorText.value = "";

  try {
    const data = await listPending({
      task_id: optional(query.task_id),
      page: query.page,
      page_size: query.page_size,
    });
    items.value = data.items;
    total.value = data.total;
  } catch (error) {
    errorText.value = (error as ApiError).message ?? "待复核列表查询失败";
    items.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}

function optional(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function submitFilters() {
  query.page = 1;
  fetchPending();
}

function resetFilters() {
  query.task_id = "";
  query.page = 1;
  fetchPending();
}

function onPageChange(page: number) {
  query.page = page;
  fetchPending();
}

function onPageSizeChange(pageSize: number) {
  query.page_size = pageSize;
  query.page = 1;
  fetchPending();
}

function openApproveDialog(item: PendingReviewItem, action: ReviewAction) {
  selectedItem.value = item;
  selectedAction.value = action;
  dialogVisible.value = true;
}

async function confirmApprove(payload: { handler_username: string; remark?: string }) {
  if (!selectedItem.value || !selectedAction.value) {
    return;
  }

  submitting.value = true;
  errorText.value = "";

  try {
    const result = await approveReview(selectedItem.value.queue_id, {
      action: selectedAction.value,
      handler_username: payload.handler_username,
      remark: payload.remark,
    });
    lastHandler.value = payload.handler_username;
    localStorage.setItem(handlerStorageKey, payload.handler_username);
    dialogVisible.value = false;
    removeOrRefresh(result);
    ElMessage.success(`处置完成：${STATUS_META[result.current_status]?.label ?? result.current_status}`);
  } catch (error) {
    errorText.value = (error as ApiError).message ?? "处置提交失败";
  } finally {
    submitting.value = false;
  }
}

function removeOrRefresh(result: ReviewResult) {
  items.value = items.value.filter((item) => item.queue_id !== result.queue_id);
  total.value = Math.max(0, total.value - 1);
  if (!items.value.length && total.value > 0) {
    fetchPending();
  }
}
</script>

<template>
  <PageHeader
    title="人工复核"
    description="查看 AI 建议与 RAG 来源，确认平账或强制挂账。当前契约不提供左右流水金额面板。"
  />

  <div class="review-page">
    <BaseCard>
      <div class="review-page__filters">
        <label>
          <span>任务 ID</span>
          <ElInput
            v-model="query.task_id"
            placeholder="可选 task_id"
            clearable
            @keyup.enter="submitFilters"
          />
        </label>
        <div class="review-page__filter-actions">
          <BaseButton variant="secondary" :disabled="loading" @click="resetFilters">重置</BaseButton>
          <BaseButton :loading="loading" @click="submitFilters">查询</BaseButton>
        </div>
      </div>
    </BaseCard>

    <div v-if="errorText" class="review-page__error" role="alert">
      <strong>操作失败</strong>
      <span>{{ errorText }}</span>
    </div>

    <div v-if="loading && !hasItems" class="review-page__skeleton" aria-label="加载待复核项">
      <div v-for="index in 3" :key="index" />
    </div>

    <div v-else-if="hasItems" class="review-page__list">
      <ReviewCard
        v-for="item in items"
        :key="item.queue_id"
        :item="item"
        @action="openApproveDialog"
      />
    </div>

    <EmptyState
      v-else
      title="暂无待复核项"
      description="当前筛选条件下没有需要人工处理的记录。"
    />

    <div class="review-page__pagination">
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

    <ApproveDialog
      v-model="dialogVisible"
      :item="selectedItem"
      :action="selectedAction"
      :loading="submitting"
      :initial-handler="lastHandler"
      @confirm="confirmApprove"
    />
  </div>
</template>

<style scoped>
.review-page {
  display: grid;
  gap: var(--space-6);
}

.review-page__filters {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--space-4);
  align-items: end;
}

.review-page__filters label {
  display: grid;
  gap: var(--space-2);
}

.review-page__filters span,
.review-page__pagination span {
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.review-page__filter-actions {
  display: flex;
  gap: var(--space-2);
}

.review-page__error {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-5);
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, var(--color-surface));
  border: 1px solid color-mix(in srgb, var(--color-danger) 28%, var(--color-border-soft));
  border-radius: var(--radius-md);
}

.review-page__error strong,
.review-page__error span {
  font-size: 14px;
  line-height: 1.5;
}

.review-page__error span {
  font-family: var(--font-mono);
}

.review-page__list {
  display: grid;
  gap: var(--space-5);
}

.review-page__skeleton {
  display: grid;
  gap: var(--space-5);
}

.review-page__skeleton div {
  position: relative;
  min-height: 300px;
  overflow: hidden;
  background: var(--color-surface-muted);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-lg);
}

.review-page__skeleton div::after {
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

.review-page__pagination {
  display: flex;
  gap: var(--space-4);
  align-items: center;
  justify-content: space-between;
}

@keyframes shimmer {
  from {
    transform: translateX(-100%);
  }

  to {
    transform: translateX(100%);
  }
}

@media (max-width: 680px) {
  .review-page__filters,
  .review-page__pagination {
    align-items: stretch;
    grid-template-columns: 1fr;
  }

  .review-page__pagination {
    display: grid;
  }
}
</style>
