<script setup lang="ts">
import { computed } from "vue";
import EmptyState from "../ui/EmptyState.vue";

const props = defineProps<{
  items: Array<{ type: string; label: string; count: number }>;
  total: number;
}>();

const maxCount = computed(() => Math.max(...props.items.map((item) => item.count), 0));

function widthFor(count: number) {
  if (!maxCount.value) {
    return "0%";
  }
  return `${Math.max(6, Math.round((count / maxCount.value) * 100))}%`;
}
</script>

<template>
  <EmptyState
    v-if="total === 0"
    title="该任务暂无异常明细"
    description="当前没有可展示的异常类型分布。"
  />
  <div v-else class="distribution">
    <div v-for="item in items" :key="item.type" class="distribution__row">
      <div class="distribution__meta">
        <span>{{ item.label }}</span>
        <strong>{{ item.count }}</strong>
      </div>
      <div class="distribution__track" aria-hidden="true">
        <div class="distribution__bar" :style="{ width: widthFor(item.count) }" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.distribution {
  display: grid;
  gap: var(--space-4);
}

.distribution__row {
  display: grid;
  gap: var(--space-2);
}

.distribution__meta {
  display: flex;
  gap: var(--space-3);
  align-items: baseline;
  justify-content: space-between;
  color: var(--color-text);
  font-size: 14px;
  line-height: 1.5;
}

.distribution__meta strong {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-weight: 650;
}

.distribution__track {
  height: 10px;
  overflow: hidden;
  background: var(--color-surface-muted);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-full);
}

.distribution__bar {
  height: 100%;
  background: var(--color-accent);
  border-radius: inherit;
  transition: width var(--duration-normal) var(--ease-standard);
}
</style>
