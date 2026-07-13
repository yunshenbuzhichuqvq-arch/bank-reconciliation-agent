<script setup lang="ts">
import { computed } from "vue";
import type { TraceSpanView } from "../types/trace";
import { SPAN_TYPE_LABEL, SPAN_STATUS_LABEL } from "../types/trace";

const props = defineProps<{ spans: TraceSpanView[] }>();

const sortedSpans = computed(() =>
  [...props.spans].sort((a, b) => a.sequence_no - b.sequence_no),
);

const spanIdSet = computed(() => new Set(props.spans.map((s) => s.span_id)));

function indentLevel(span: TraceSpanView): number {
  if (!span.parent_span_id || span.parent_span_id === props.spans[0]?.span_id) {
    return 0;
  }
  return 1;
}

function durationText(ms: number): string {
  if (ms < 1000) {
    return `${ms}ms`;
  }
  return `${(ms / 1000).toFixed(2)}s`;
}

function evidenceText(ids: string[]): string {
  if (!ids.length) {
    return "无引用";
  }
  return ids.join(", ");
}

async function copyId(id: string) {
  try {
    await navigator.clipboard.writeText(id);
  } catch {
    // clipboard API unsupported — silently degrade
  }
}

function onCopyKeydown(e: KeyboardEvent, id: string) {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    copyId(id);
  }
}
</script>

<template>
  <ul v-if="sortedSpans.length" class="timeline" aria-label="执行轨迹">
    <li
      v-for="span in sortedSpans"
      :key="span.span_id"
      class="timeline__item"
      :style="{ marginLeft: indentLevel(span) * 24 + 'px' }"
    >
      <div class="timeline__marker" :class="`timeline__marker--${span.status.toLowerCase()}`" />

      <div class="timeline__body">
        <div class="timeline__head">
          <span class="timeline__type">{{ SPAN_TYPE_LABEL[span.span_type] }}</span>
          <span class="timeline__name">{{ span.name }}</span>
          <span class="timeline__status" :class="`status--${span.status.toLowerCase()}`">
            {{ SPAN_STATUS_LABEL[span.status] }}
          </span>
          <span v-if="span.outcome" class="timeline__outcome">{{ span.outcome }}</span>
        </div>

        <div class="timeline__meta">
          <span>#{{ span.sequence_no }}</span>
          <span>{{ durationText(span.duration_ms) }}</span>
          <span v-if="span.attempt > 1">第 {{ span.attempt }} 次尝试</span>
          <span v-if="span.retry_recovered">(已恢复)</span>
          <span v-if="span.model_name">{{ span.model_name }}</span>
        </div>

        <div v-if="span.prompt_tokens !== null || span.completion_tokens !== null" class="timeline__tokens">
          <span v-if="span.prompt_tokens !== null">🠿 {{ span.prompt_tokens }}</span>
          <span v-if="span.completion_tokens !== null">🠿 {{ span.completion_tokens }}</span>
          <span v-if="span.cached_calls">缓存 ×{{ span.cached_calls }}</span>
        </div>

        <div v-if="span.result_count !== null && span.span_type === 'TOOL'" class="timeline__tokens">
          <span>结果数: {{ span.result_count }}</span>
        </div>

        <div v-if="span.error_type || span.fallback_reason" class="timeline__error">
          <span v-if="span.error_type">{{ span.error_type }}</span>
          <span v-if="span.fallback_reason">{{ span.fallback_reason }}</span>
        </div>

        <div class="timeline__evidence">
          <span class="timeline__evidence-label">证据:</span>
          <button
            v-if="span.evidence_ids.length"
            class="timeline__evidence-ids"
            @click="copyId(span.evidence_ids.join(', '))"
            @keydown="onCopyKeydown($event, span.evidence_ids.join(', '))"
            :aria-label="`复制证据 ID: ${evidenceText(span.evidence_ids)}`"
          >
            {{ evidenceText(span.evidence_ids) }}
          </button>
          <span v-else class="timeline__evidence-empty">无引用</span>
        </div>
      </div>
    </li>
  </ul>
  <p v-else class="timeline__empty">暂无执行节点</p>
</template>

<style scoped>
.timeline {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 0;
}

.timeline__item {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-3) 0 var(--space-3) var(--space-3);
  border-left: 2px solid var(--color-border-soft);
}

.timeline__item:first-child { padding-top: 0; }
.timeline__item:last-child { border-left-color: transparent; }

.timeline__marker {
  width: 10px;
  height: 10px;
  border-radius: var(--radius-full);
  margin-top: 5px;
  flex-shrink: 0;
  background: var(--color-info);
}
.timeline__marker--failed { background: var(--color-danger); }
.timeline__marker--succeeded { background: var(--color-success); }
.timeline__marker--cancelled { background: var(--color-text-muted); }

.timeline__body {
  display: grid;
  gap: var(--space-1);
  min-width: 0;
  flex: 1;
}

.timeline__head {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  flex-wrap: wrap;
}

.timeline__type {
  color: var(--color-text);
  font-size: 12px;
  font-weight: 600;
  background: var(--color-bg-soft);
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  white-space: nowrap;
}

.timeline__name {
  color: var(--color-text-muted);
  font-size: 13px;
  font-family: var(--font-mono);
}

.timeline__status {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.status--succeeded { color: var(--color-success); }
.status--failed { color: var(--color-danger); }
.status--cancelled { color: var(--color-text-muted); }

.timeline__outcome {
  font-size: 11px;
  color: var(--color-text-muted);
  background: var(--color-bg-soft);
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
}

.timeline__meta,
.timeline__tokens,
.timeline__error {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.timeline__tokens { color: var(--color-text); }
.timeline__error { color: var(--color-danger); }

.timeline__evidence {
  font-size: 12px;
  color: var(--color-text-muted);
  display: flex;
  gap: var(--space-2);
}

.timeline__evidence-label {
  flex-shrink: 0;
}

.timeline__evidence-ids {
  font-family: var(--font-mono);
  color: var(--color-primary);
  cursor: pointer;
  overflow-wrap: anywhere;
  word-break: break-all;
  background: none;
  border: none;
  padding: 0;
  font-size: inherit;
  text-align: left;
}

.timeline__evidence-ids:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
  border-radius: 2px;
}

.timeline__evidence-empty {
  font-style: italic;
}

.timeline__empty {
  color: var(--color-text-muted);
  text-align: center;
  padding: var(--space-6);
}

@media (max-width: 640px) {
  .timeline__meta,
  .timeline__head {
    gap: var(--space-1);
  }
}
</style>
