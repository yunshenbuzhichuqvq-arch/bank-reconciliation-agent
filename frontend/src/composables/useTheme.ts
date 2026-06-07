import { computed, ref } from "vue";

type ThemeName = "light" | "dark";

const storageKey = "bank-reconciliation-theme";
const currentTheme = ref<ThemeName>(readInitialTheme());

applyTheme(currentTheme.value);

export function useTheme() {
  const isDark = computed(() => currentTheme.value === "dark");

  function setTheme(theme: ThemeName) {
    currentTheme.value = theme;
    localStorage.setItem(storageKey, theme);
    applyTheme(theme);
  }

  function toggleTheme() {
    setTheme(isDark.value ? "light" : "dark");
  }

  return {
    theme: currentTheme,
    isDark,
    setTheme,
    toggleTheme,
  };
}

function readInitialTheme(): ThemeName {
  const stored = localStorage.getItem(storageKey);
  if (stored === "dark" || stored === "light") {
    return stored;
  }
  return "light";
}

function applyTheme(theme: ThemeName) {
  document.documentElement.dataset.theme = theme;
}
