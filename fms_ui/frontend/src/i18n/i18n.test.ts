import { beforeEach, describe, expect, it } from "vitest";

import { getLocale, messages, setLocale, t } from "@/i18n";
import { useTheme } from "@/composables/useTheme";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.dataset.theme = "light";
  setLocale("en");
});

describe("i18n", () => {
  it("keeps the zh-CN and en message keys in sync", () => {
    expect(Object.keys(messages["zh-CN"]).sort()).toEqual(Object.keys(messages.en).sort());
  });

  it("persists the chosen locale and translates immediately", () => {
    expect(getLocale()).toBe("en");
    setLocale("zh-CN");
    expect(getLocale()).toBe("zh-CN");
    expect(window.localStorage.getItem("fms-ui-locale")).toBe("zh-CN");
    expect(document.documentElement.lang).toBe("zh-CN");
    expect(t("searchButton")).toBe("搜索");
    expect(t("sessionCount", { count: 2, mode: t("metadataSearch") })).toBe(
      "2 个会话 · 元数据检索",
    );
  });

  it("detects the locale from the browser languages when nothing is stored", async () => {
    const { vi } = await import("vitest");
    window.localStorage.clear();
    vi.resetModules();
    Object.defineProperty(navigator, "languages", {
      value: ["zh-Hans-CN", "en"],
      configurable: true,
    });
    const fresh = await import("@/i18n/index");
    expect(fresh.getLocale()).toBe("zh-CN");
  });
});

describe("useTheme", () => {
  it("toggles the document theme and persists the choice", () => {
    const { theme, themeToggleLabel, toggleTheme } = useTheme();
    expect(theme.value).toBe("light");
    expect(themeToggleLabel.value).toBe("Switch to dark mode");

    toggleTheme();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("fms-ui-theme")).toBe("dark");
    expect(theme.value).toBe("dark");
    expect(themeToggleLabel.value).toBe("Switch to light mode");
  });
});
