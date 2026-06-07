<script setup lang="ts">
defineProps<{
  label: string;
  value: string | number;
  note?: string;
}>();
</script>

<template>
  <section class="stat-card">
    <p class="stat-card__label">{{ label }}</p>
    <p class="stat-card__value">{{ value }}</p>
    <p v-if="note" class="stat-card__note">{{ note }}</p>
  </section>
</template>

<style scoped>
.stat-card {
  min-width: 0;
  padding: var(--space-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
}

.stat-card__label,
.stat-card__note {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.stat-card__value {
  margin: var(--space-2) 0 0;
  overflow-wrap: anywhere;
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: 28px;
  font-variant-numeric: tabular-nums;
  font-weight: 650;
  line-height: 1.15;
}

.stat-card__note {
  margin-top: var(--space-2);
}
</style>
