<script setup lang="ts">
import { computed } from "vue";
import { STATUS_META } from "../../constants/enums";

const props = defineProps<{ value:string }>();
const meta = computed(() => STATUS_META[props.value] ?? { label: props.value, tone: "neutral" });
</script>

<template>
  <span class="badge" :class="`badge--${meta.tone}`">{{ meta.label }}</span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 var(--space-2);
  border: 1px solid var(--tone-border, var(--color-border));
  border-radius: var(--radius-full);
  background: color-mix(in srgb, var(--tone-color, var(--color-text-muted)) 12%, transparent);
  color: var(--tone-color, var(--color-text-muted));
  font-size: 12px;
  font-weight: 500;
}

.badge--success { --tone-color: var(--color-success); --tone-border: color-mix(in srgb, var(--color-success) 30%, var(--color-border)); }
.badge--warning { --tone-color: var(--color-warning); --tone-border: color-mix(in srgb, var(--color-warning) 30%, var(--color-border)); }
.badge--danger { --tone-color: var(--color-danger); --tone-border: color-mix(in srgb, var(--color-danger) 30%, var(--color-border)); }
.badge--info { --tone-color: var(--color-info); --tone-border: color-mix(in srgb, var(--color-info) 30%, var(--color-border)); }
.badge--neutral { --tone-color: var(--color-text-muted); --tone-border: var(--color-border); }
</style>
