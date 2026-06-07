<script setup lang="ts">
withDefaults(defineProps<{
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md";
  loading?: boolean;
  disabled?: boolean;
}>(), {
  variant: "primary",
  size: "md",
  loading: false,
  disabled: false,
});
</script>

<template>
  <button
    class="base-button"
    :class="[`base-button--${variant}`, `base-button--${size}`]"
    :disabled="disabled || loading"
    type="button"
  >
    <span class="base-button__content" :class="{ 'is-hidden': loading }">
      <slot />
    </span>
    <span v-if="loading" class="base-button__loader" aria-label="加载中" />
  </button>
</template>

<style scoped>
.base-button {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  transition: background var(--duration-fast) var(--ease-standard),
    border-color var(--duration-fast) var(--ease-standard),
    color var(--duration-fast) var(--ease-standard),
    transform var(--duration-fast) var(--ease-standard);
}

.base-button--md {
  min-height: 40px;
  padding: 0 var(--space-4);
}

.base-button--sm {
  min-height: 32px;
  padding: 0 var(--space-3);
}

.base-button--primary {
  background: var(--color-text);
  border-color: var(--color-text);
  color: var(--color-bg-soft);
}

.base-button--secondary {
  background: transparent;
  border-color: var(--color-border);
  color: var(--color-text);
}

.base-button--ghost {
  background: transparent;
  color: var(--color-text-muted);
}

.base-button:hover:not(:disabled) {
  transform: translateY(-1px);
}

.base-button--primary:hover:not(:disabled) {
  background: var(--color-accent);
  border-color: var(--color-accent);
}

.base-button--secondary:hover:not(:disabled),
.base-button--ghost:hover:not(:disabled) {
  background: var(--color-surface-muted);
  border-color: var(--color-border-soft);
}

.base-button:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.base-button__content.is-hidden {
  visibility: hidden;
}

.base-button__loader {
  position: absolute;
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: spin var(--duration-slow) linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
