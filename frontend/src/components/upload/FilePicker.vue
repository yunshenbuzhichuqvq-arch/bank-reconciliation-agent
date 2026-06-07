<script setup lang="ts">
import { computed, ref } from "vue";
import BaseButton from "../ui/BaseButton.vue";

const props = defineProps<{
  modelValue: File | null;
  label: string;
  description: string;
  inputId: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [file: File | null];
}>();

const inputRef = ref<HTMLInputElement | null>(null);

const fileSize = computed(() => {
  if (!props.modelValue) {
    return "";
  }
  const kb = props.modelValue.size / 1024;
  if (kb < 1024) {
    return `${Math.max(1, Math.round(kb))} KB`;
  }
  return `${(kb / 1024).toFixed(1)} MB`;
});

function openPicker() {
  inputRef.value?.click();
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  emit("update:modelValue", input.files?.[0] ?? null);
}

function clearFile() {
  if (inputRef.value) {
    inputRef.value.value = "";
  }
  emit("update:modelValue", null);
}
</script>

<template>
  <section class="file-picker" :class="{ 'has-file': modelValue }">
    <div class="file-picker__text">
      <label class="file-picker__label" :for="inputId">{{ label }}</label>
      <p>{{ description }}</p>
    </div>

    <input
      :id="inputId"
      ref="inputRef"
      class="file-picker__input"
      type="file"
      accept=".xlsx,.xls"
      @change="onFileChange"
    >

    <div v-if="modelValue" class="file-picker__file">
      <div>
        <p class="file-picker__name">{{ modelValue.name }}</p>
        <p class="file-picker__meta">{{ fileSize }}</p>
      </div>
      <BaseButton variant="ghost" size="sm" @click="clearFile">清除</BaseButton>
    </div>
    <BaseButton v-else variant="secondary" size="sm" @click="openPicker">选择文件</BaseButton>
  </section>
</template>

<style scoped>
.file-picker {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--space-4);
  align-items: center;
  min-height: 112px;
  padding: var(--space-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  transition: border-color var(--duration-fast) var(--ease-standard),
    background var(--duration-fast) var(--ease-standard);
}

.file-picker.has-file {
  background: var(--color-bg-soft);
  border-color: var(--color-text-muted);
}

.file-picker:focus-within {
  border-color: var(--color-text-muted);
  box-shadow: 0 0 0 3px rgba(43, 41, 38, 0.08);
}

.file-picker__label {
  display: block;
  margin-bottom: var(--space-2);
  color: var(--color-text);
  font-size: 15px;
  font-weight: 600;
}

.file-picker__text p,
.file-picker__meta {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.file-picker__input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}

.file-picker__file {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: flex-end;
  min-width: 260px;
}

.file-picker__name {
  max-width: 220px;
  margin: 0 0 var(--space-1);
  overflow: hidden;
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 720px) {
  .file-picker {
    grid-template-columns: 1fr;
    align-items: stretch;
  }

  .file-picker__file {
    justify-content: space-between;
    min-width: 0;
  }

  .file-picker__name {
    max-width: 60vw;
  }
}
</style>
