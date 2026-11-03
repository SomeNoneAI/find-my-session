import { ref } from "vue";

import { locales, messages } from "./messages";
import type { LocaleCode } from "./messages";

export { locales };
export { messages };

const STORAGE_KEY = "fms-ui-locale";

function isSupported(code: string): code is LocaleCode {
  return Object.prototype.hasOwnProperty.call(messages, code);
}

function readStoredLocale(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch (error) {
    return null;
  }
}

function writeStoredLocale(code: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, code);
  } catch (error) {
    // Storage unavailable (private mode, blocked cookies): keep the in-memory locale only.
  }
}

function detectLocale(): LocaleCode {
  const stored = readStoredLocale();
  if (stored && isSupported(stored)) return stored;
  const candidates =
    Array.isArray(navigator.languages) && navigator.languages.length
      ? navigator.languages
      : [navigator.language || ""];
  for (const candidate of candidates) {
    if (!candidate) continue;
    if (candidate.toLowerCase().startsWith("zh")) return "zh-CN";
    if (isSupported(candidate)) return candidate;
  }
  return "en";
}

export const locale = ref<LocaleCode>(detectLocale());

if (typeof document !== "undefined" && document.documentElement) {
  document.documentElement.lang = locale.value;
}

export function getLocale(): LocaleCode {
  return locale.value;
}

export function setLocale(code: string): boolean {
  if (!isSupported(code) || code === locale.value) return false;
  locale.value = code;
  writeStoredLocale(code);
  if (typeof document !== "undefined" && document.documentElement) {
    document.documentElement.lang = code;
  }
  return true;
}

function lookup(key: string): string {
  const current = messages[locale.value];
  if (Object.prototype.hasOwnProperty.call(current, key)) return current[key];
  if (Object.prototype.hasOwnProperty.call(messages.en, key)) return messages.en[key];
  if (Object.prototype.hasOwnProperty.call(messages["zh-CN"], key)) {
    return messages["zh-CN"][key];
  }
  return key;
}

export function t(key: string, params: Record<string, string | number> = {}): string {
  let template = lookup(key);
  if (params && typeof params === "object") {
    template = template.replace(/\{(\w+)\}/g, (match, name: string) =>
      Object.prototype.hasOwnProperty.call(params, name)
        ? String(params[name])
        : match,
    );
  }
  return template;
}
