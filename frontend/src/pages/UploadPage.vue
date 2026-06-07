<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { uploadReconciliation } from "../api/reconcile";
import type { ApiError } from "../api/client";
import type { UploadResult } from "../types/api";
import FilePicker from "../components/upload/FilePicker.vue";
import BaseButton from "../components/ui/BaseButton.vue";
import BaseCard from "../components/ui/BaseCard.vue";
import PageHeader from "../components/ui/PageHeader.vue";

const router = useRouter();

const scenario = ref<"BANK_ENTERPRISE">("BANK_ENTERPRISE");
const bankFile = ref<File | null>(null);
const clearFile = ref<File | null>(null);
const loading = ref(false);
const errorText = ref("");
const result = ref<UploadResult | null>(null);

const canSubmit = computed(() => Boolean(bankFile.value && clearFile.value && !loading.value));

const stats = computed(() => {
  if (!result.value) {
    return [];
  }
  return [
    { label: "银行端流水", value: result.value.total_bank_rows },
    { label: "企业/清算端流水", value: result.value.total_clear_rows },
    { label: "自动修复", value: result.value.auto_fixed_rows },
    { label: "待 AI 审核", value: result.value.pending_ai_rows },
    { label: "待人工复核", value: result.value.pending_human_rows },
  ];
});

async function submitUpload() {
  if (!bankFile.value || !clearFile.value || loading.value) {
    return;
  }

  loading.value = true;
  errorText.value = "";

  try {
    result.value = await uploadReconciliation(bankFile.value, clearFile.value);
  } catch (error) {
    const apiError = error as ApiError;
    errorText.value = apiError.message;
  } finally {
    loading.value = false;
  }
}

function resetForm() {
  result.value = null;
  errorText.value = "";
  bankFile.value = null;
  clearFile.value = null;
}

function goToTask() {
  if (result.value) {
    router.push(`/tasks/${result.value.task_id}`);
  }
}
</script>

<template>
  <PageHeader
    title="上传对账单"
    description="选择银企对账场景，并上传银行端与企业/清算端 Excel。系统会先校验字段，再生成对账任务。"
  />

  <form v-if="!result" class="upload-page" @submit.prevent="submitUpload">
    <div v-if="errorText" class="upload-page__error" role="alert">
      <strong>上传失败，请检查文件格式与必填列后重试</strong>
      <span>{{ errorText }}</span>
    </div>

    <BaseCard title="对账场景">
      <label class="scenario-option">
        <input v-model="scenario" type="radio" value="BANK_ENTERPRISE">
        <span>
          <strong>银企对账</strong>
          <small>银行端流水与企业/清算端流水逐笔比对</small>
        </span>
      </label>
    </BaseCard>

    <BaseCard title="上传文件">
      <div class="file-grid">
        <FilePicker
          v-model="bankFile"
          input-id="bank-file"
          label="银行端流水"
          description="对应 multipart 字段 bank_file。支持 .xlsx / .xls。"
        />
        <FilePicker
          v-model="clearFile"
          input-id="clear-file"
          label="企业/清算端流水"
          description="对应 multipart 字段 clear_file。支持 .xlsx / .xls。"
        />
      </div>

      <template #footer>
        <div class="upload-page__actions">
          <p>两份文件齐全后才能开始上传。</p>
          <BaseButton :disabled="!canSubmit" :loading="loading" @click="submitUpload">
            开始上传
          </BaseButton>
        </div>
      </template>
    </BaseCard>
  </form>

  <BaseCard v-else title="上传完成">
    <div class="result-summary">
      <div>
        <p class="result-summary__label">任务 ID</p>
        <p class="result-summary__task">{{ result.task_id }}</p>
      </div>
      <span class="result-summary__status">{{ result.status }}</span>
    </div>

    <dl class="stats-grid">
      <div v-for="item in stats" :key="item.label" class="stats-grid__item">
        <dt>{{ item.label }}</dt>
        <dd>{{ item.value }}</dd>
      </div>
    </dl>

    <template #footer>
      <div class="upload-page__actions">
        <BaseButton variant="secondary" @click="resetForm">重新上传</BaseButton>
        <BaseButton @click="goToTask">前往任务看板</BaseButton>
      </div>
    </template>
  </BaseCard>
</template>

<style scoped>
.upload-page {
  display: grid;
  gap: var(--space-6);
}

.upload-page__error {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-5);
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, var(--color-surface));
  border: 1px solid color-mix(in srgb, var(--color-danger) 28%, var(--color-border-soft));
  border-radius: var(--radius-md);
}

.upload-page__error strong,
.upload-page__error span {
  font-size: 14px;
  line-height: 1.5;
}

.upload-page__error span {
  font-family: var(--font-mono);
}

.scenario-option {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  max-width: 520px;
  cursor: pointer;
}

.scenario-option input {
  width: 16px;
  height: 16px;
  margin: 3px 0 0;
  accent-color: var(--color-text);
}

.scenario-option span {
  display: grid;
  gap: var(--space-1);
}

.scenario-option strong {
  color: var(--color-text);
  font-size: 15px;
  font-weight: 600;
}

.scenario-option small,
.upload-page__actions p,
.result-summary__label,
.stats-grid dt {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.file-grid {
  display: grid;
  gap: var(--space-4);
}

.upload-page__actions {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
}

.result-summary {
  display: flex;
  gap: var(--space-4);
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-6);
}

.result-summary__task {
  margin: var(--space-1) 0 0;
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: 14px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.result-summary__status {
  padding: var(--space-1) var(--space-3);
  color: var(--color-success);
  background: color-mix(in srgb, var(--color-success) 12%, var(--color-surface));
  border: 1px solid color-mix(in srgb, var(--color-success) 24%, var(--color-border-soft));
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--space-3);
  margin: 0;
}

.stats-grid__item {
  min-width: 0;
  padding: var(--space-4);
  background: var(--color-bg-soft);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
}

.stats-grid dd {
  margin: var(--space-2) 0 0;
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: 24px;
  font-variant-numeric: tabular-nums;
  font-weight: 650;
  line-height: 1.2;
}

@media (max-width: 900px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .upload-page__actions,
  .result-summary {
    align-items: stretch;
    flex-direction: column;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
