<script setup lang="ts">
import { computed } from "vue";
import { RISK_META } from "../../constants/enums";

const props = defineProps<{ level:string }>();
const meta = computed(() => RISK_META[props.level] ?? { label: props.level, tone: "neutral" });
</script>

<template>
  <span class="risk" :class="`risk--${meta.tone}`">风险 {{ meta.label }}</span>
</template>

<style scoped>
.risk {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 var(--space-2);
  border: 1px solid var(--tone-border, var(--color-border));
  border-radius: var(--radius-sm);
  color: var(--tone-color, var(--color-text-muted));
  font-size: 12px;
  font-weight: 500;
}

.risk--success { --tone-color: var(--color-success); --tone-border: color-mix(in srgb, var(--color-success) 28%, var(--color-border)); }
.risk--warning { --tone-color: var(--color-warning); --tone-border: color-mix(in srgb, var(--color-warning) 28%, var(--color-border)); }
.risk--danger { --tone-color: var(--color-danger); --tone-border: color-mix(in srgb, var(--color-danger) 28%, var(--color-border)); }
.risk--info { --tone-color: var(--color-info); --tone-border: color-mix(in srgb, var(--color-info) 28%, var(--color-border)); }
.risk--neutral { --tone-color: var(--color-text-muted); --tone-border: var(--color-border); }
</style>
