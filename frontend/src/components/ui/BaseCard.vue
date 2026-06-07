<script setup lang="ts">
defineProps<{ title?: string }>();
</script>

<template>
  <section class="base-card">
    <header v-if="$slots.header || title" class="base-card__header">
      <slot name="header">
        <h2>{{ title }}</h2>
      </slot>
    </header>
    <div class="base-card__body">
      <slot />
    </div>
    <footer v-if="$slots.footer" class="base-card__footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<style scoped>
.base-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
}

.base-card__header,
.base-card__footer {
  padding: var(--space-5) var(--space-6);
}

.base-card__header {
  border-bottom: 1px solid var(--color-border-soft);
}

.base-card__footer {
  border-top: 1px solid var(--color-border-soft);
}

.base-card__body {
  padding: var(--space-6);
}

h2 {
  margin: 0;
  color: var(--color-text);
  font-size: 16px;
  font-weight: 600;
}
</style>
