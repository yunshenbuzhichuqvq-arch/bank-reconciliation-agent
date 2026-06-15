<script setup lang="ts">
import type { AgentStreamEvent } from "../../types/api";
import EmptyState from "../ui/EmptyState.vue";
import EventCard from "./EventCard.vue";

defineProps<{ events: readonly AgentStreamEvent[] }>();
</script>

<template>
  <section class="event-timeline" aria-label="Agent 流式事件">
    <div v-if="events.length" class="event-timeline__list">
      <EventCard
        v-for="event in events"
        :key="`${event.seq}-${event.event_type}`"
        :event="event"
      />
    </div>
    <EmptyState
      v-else
      title="等待流式审计"
      description="选择两份 Excel 文件后启动审计，Hook、RAG、决策和 Fallback 事件会按时间顺序显示在这里。"
    />
  </section>
</template>

<style scoped>
.event-timeline {
  min-height: 360px;
}

.event-timeline__list {
  position: relative;
  display: grid;
  gap: var(--space-4);
  padding-left: var(--space-5);
}

.event-timeline__list::before {
  position: absolute;
  top: var(--space-2);
  bottom: var(--space-2);
  left: 4px;
  width: 1px;
  background: var(--color-border-soft);
  content: "";
}
</style>
