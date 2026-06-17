<script setup lang="ts">
import { Moon, Sunny } from "@element-plus/icons-vue";
import { useRoute } from "vue-router";

import { useTheme } from "../composables/useTheme";
import BaseButton from "./ui/BaseButton.vue";

const route = useRoute();
const { isDark, toggleTheme } = useTheme();

const navItems = [
  { label: "上传对账单", to: "/upload" },
  { label: "Agent 工作台", to: "/workbench" },
  { label: "差错台账", to: "/ledger" },
  { label: "人工复核", to: "/review" },
  { label: "量化指标", to: "/metrics" },
];
</script>

<template>
  <div class="app-shell">
    <aside class="app-shell__sidebar">
      <div class="app-shell__brand">
        <span class="app-shell__brand-mark">账</span>
        <div>
          <strong>银企对账</strong>
          <span>审计辅助工作台</span>
        </div>
      </div>

      <nav class="app-shell__nav" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          class="app-shell__nav-link"
          :class="{ 'is-active': route.path === item.to }"
          :to="item.to"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>

    <div class="app-shell__main">
      <div class="app-shell__topbar">
        <span class="app-shell__context">X-User-ID: demo_user</span>
        <BaseButton variant="ghost" size="sm" @click="toggleTheme">
          <el-icon aria-hidden="true">
            <Moon v-if="!isDark" />
            <Sunny v-else />
          </el-icon>
          {{ isDark ? "浅色" : "深色" }}
        </BaseButton>
      </div>

      <main class="app-shell__content">
        <slot />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  min-height: 100vh;
}

.app-shell__sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  padding: var(--space-6);
  border-right: 1px solid var(--color-border-soft);
  background: color-mix(in srgb, var(--color-bg-soft) 92%, var(--color-surface));
}

.app-shell__brand {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-10);
}

.app-shell__brand-mark {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-accent);
  font-family: var(--font-serif);
  font-size: 19px;
  box-shadow: var(--shadow-soft);
}

.app-shell__brand strong,
.app-shell__brand span {
  display: block;
}

.app-shell__brand strong {
  color: var(--color-text);
  font-size: 15px;
  font-weight: 650;
}

.app-shell__brand span {
  margin-top: var(--space-1);
  color: var(--color-text-subtle);
  font-size: 12px;
}

.app-shell__nav {
  display: grid;
  gap: var(--space-1);
}

.app-shell__nav-link {
  display: flex;
  align-items: center;
  min-height: 40px;
  padding: 0 var(--space-3);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  font-size: 14px;
  font-weight: 500;
  transition: background var(--duration-fast) var(--ease-standard),
    border-color var(--duration-fast) var(--ease-standard),
    color var(--duration-fast) var(--ease-standard);
}

.app-shell__nav-link:hover {
  background: var(--color-surface-muted);
  color: var(--color-text);
}

.app-shell__nav-link.is-active {
  background: var(--color-surface);
  border-color: var(--color-border-soft);
  color: var(--color-text);
  box-shadow: var(--shadow-soft);
}

.app-shell__main {
  min-width: 0;
}

.app-shell__topbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-3);
  min-height: 64px;
  padding: 0 var(--space-10);
}

.app-shell__context {
  color: var(--color-text-subtle);
  font-family: var(--font-mono);
  font-size: 12px;
}

.app-shell__content {
  width: min(var(--content-wide-max-width), calc(100% - var(--space-10) * 2));
  margin: 0 auto;
  padding: var(--space-6) 0 var(--space-12);
}

@media (max-width: 820px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .app-shell__sidebar {
    position: static;
    height: auto;
    padding: var(--space-4);
    border-right: 0;
    border-bottom: 1px solid var(--color-border-soft);
  }

  .app-shell__nav {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }

  .app-shell__nav-link {
    justify-content: center;
    text-align: center;
  }

  .app-shell__topbar {
    padding: 0 var(--space-4);
  }

  .app-shell__content {
    width: min(100% - var(--space-4) * 2, var(--content-wide-max-width));
  }
}
</style>
