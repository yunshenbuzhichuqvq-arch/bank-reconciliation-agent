<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { PendingReviewItem, ReviewAction } from "../../types/api";
import { ACTION_LABEL, ERROR_TYPE_LABEL } from "../../constants/enums";
import BaseButton from "../ui/BaseButton.vue";

const props = defineProps<{
  modelValue: boolean;
  item: PendingReviewItem | null;
  action: ReviewAction | null;
  loading?: boolean;
  initialHandler: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  confirm: [payload: { handler_username: string; remark?: string }];
}>();

const handlerUsername = ref(props.initialHandler || "reviewer");
const remark = ref("");
const touched = ref(false);

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});

const actionLabel = computed(() => {
  if (!props.action) {
    return "";
  }
  return ACTION_LABEL[props.action] ?? props.action;
});

const handlerError = computed(() => touched.value && !handlerUsername.value.trim());

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      handlerUsername.value = props.initialHandler || "reviewer";
      remark.value = "";
      touched.value = false;
    }
  },
);

function submit() {
  touched.value = true;
  const handler = handlerUsername.value.trim();
  if (!handler) {
    return;
  }
  const note = remark.value.trim();
  emit("confirm", {
    handler_username: handler,
    remark: note || undefined,
  });
}
</script>

<template>
  <ElDialog v-model="visible" title="确认处置" width="520px" destroy-on-close>
    <div v-if="item && action" class="approve-dialog">
      <p class="approve-dialog__summary">
        将对队列 <span class="cell-mono">#{{ item.queue_id }}</span>
        执行 <strong>{{ actionLabel }}</strong>。
      </p>
      <dl>
        <div>
          <dt>异常类型</dt>
          <dd>{{ ERROR_TYPE_LABEL[item.error_type] ?? item.error_type }}</dd>
        </div>
        <div>
          <dt>规则分支</dt>
          <dd class="cell-mono">{{ item.exception_branch ?? "—" }}</dd>
        </div>
      </dl>

      <label class="approve-dialog__field">
        <span>处理人</span>
        <ElInput
          v-model="handlerUsername"
          placeholder="reviewer"
          :class="{ 'is-error': handlerError }"
          @blur="touched = true"
          @keyup.enter="submit"
        />
        <small v-if="handlerError">处理人必填。</small>
      </label>

      <label class="approve-dialog__field">
        <span>备注</span>
        <ElInput
          v-model="remark"
          type="textarea"
          :rows="3"
          placeholder="可选"
        />
      </label>
    </div>

    <template #footer>
      <div class="approve-dialog__actions">
        <BaseButton variant="secondary" :disabled="loading" @click="visible = false">取消</BaseButton>
        <BaseButton :loading="loading" @click="submit">确认提交</BaseButton>
      </div>
    </template>
  </ElDialog>
</template>

<style scoped>
.approve-dialog {
  display: grid;
  gap: var(--space-5);
}

.approve-dialog__summary {
  margin: 0;
  color: var(--color-text);
  font-size: 14px;
  line-height: 1.7;
}

.approve-dialog__summary strong {
  font-weight: 600;
}

dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
  margin: 0;
}

dl div {
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

.approve-dialog__field {
  display: grid;
  gap: var(--space-2);
}

.approve-dialog__field span {
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.approve-dialog__field small {
  color: var(--color-danger);
  font-size: 12px;
}

.approve-dialog__actions {
  display: flex;
  gap: var(--space-3);
  justify-content: flex-end;
}

.is-error :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px var(--color-danger) inset;
}

@media (max-width: 560px) {
  dl {
    grid-template-columns: 1fr;
  }
}
</style>
