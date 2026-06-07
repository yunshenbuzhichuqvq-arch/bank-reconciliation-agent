<script setup lang="ts">
defineProps<{ title:string; description?:string }>();
</script>

<template>
  <div class="empty-state">
    <div class="empty-state__mark" aria-hidden="true" />
    <h2>{{ title }}</h2>
    <p v-if="description">{{ description }}</p>
    <div v-if="$slots.action" class="empty-state__action">
      <slot name="action" />
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  display: grid;
  justify-items: center;
  padding: var(--space-12) var(--space-6);
  text-align: center;
}

.empty-state__mark {
  width: 44px;
  height: 44px;
  margin-bottom: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background:
    linear-gradient(90deg, transparent 48%, var(--color-border-soft) 48% 52%, transparent 52%),
    linear-gradient(0deg, transparent 48%, var(--color-border-soft) 48% 52%, transparent 52%),
    var(--color-surface-muted);
}

h2 {
  margin: 0;
  color: var(--color-text);
  font-size: 18px;
  font-weight: 600;
}

p {
  max-width: 420px;
  margin: var(--space-2) 0 0;
  color: var(--color-text-muted);
  line-height: 1.6;
}

.empty-state__action {
  margin-top: var(--space-5);
}
</style>
