import { computed, ref } from "vue";

import { t } from "@/i18n";
import { writeStoredFlag } from "@/utils";

export type Theme = "light" | "dark";

export function currentTheme(): Theme {
  if (typeof document === "undefined" || !document.documentElement) return "light";
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  if (typeof document === "undefined" || !document.documentElement) return;
  const root = document.documentElement;
  root.classList.add("theme-switching");
  void root.offsetWidth;
  root.dataset.theme = theme;
  writeStoredFlag("fms-ui-theme", theme);
  root.classList.remove("theme-switching");
}

export function useTheme() {
  const theme = ref<Theme>(currentTheme());

  const themeToggleLabel = computed(() =>
    theme.value === "dark" ? t("switchToLight") : t("switchToDark"),
  );

  function setTheme(value: Theme): void {
    applyTheme(value);
    theme.value = value;
  }

  function toggleTheme(): void {
    setTheme(theme.value === "dark" ? "light" : "dark");
  }

  return { theme, themeToggleLabel, toggleTheme };
}
