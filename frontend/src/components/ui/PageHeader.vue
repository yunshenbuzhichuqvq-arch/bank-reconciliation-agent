<script setup lang="ts">
defineProps<{ title:string; description?:string }>();
</script>

<template>
  <header class="page-header">
    <div>
      <p class="page-header__eyebrow">MVP-1 银企对账</p>
      <h1>{{ title }}</h1>
      <p v-if="description" class="page-header__description">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="page-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  gap: var(--space-6);
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-8);
}

.page-header__eyebrow {
  margin: 0 0 var(--space-2);
  color: var(--color-text-subtle);
  font-size: 12px;
  font-weight: 600;
}

h1 {
  margin: 0;
  color: var(--color-text);
  font-size: 28px;
  font-weight: 650;
  letter-spacing: 0;
  line-height: 1.25;
}

.page-header__description {
  max-width: 640px;
  margin: var(--space-3) 0 0;
  color: var(--color-text-muted);
  font-size: 15px;
  line-height: 1.6;
}

.page-header__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  justify-content: flex-end;
}
</style>
