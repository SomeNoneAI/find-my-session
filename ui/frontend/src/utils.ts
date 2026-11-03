import { getLocale, t } from "@/i18n";

export function readStoredFlag(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "true";
  } catch (error) {
    return false;
  }
}

export function readStoredValue(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch (error) {
    return null;
  }
}

export function writeStoredFlag(key: string, value: boolean | string): void {
  try {
    window.localStorage.setItem(key, String(value));
  } catch (error) {
    return;
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

export function queryString(
  values: Record<string, string | number | boolean | null | undefined>,
): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== "" && value !== false && value !== null && value !== undefined) {
      params.set(key, String(value));
    }
  }
  return params.toString();
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return t("unknown");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(getLocale(), {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function relativeDate(value: string | null | undefined): string {
  if (!value) return t("unknownTime");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const ranges: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 31536000],
    ["month", 2592000],
    ["week", 604800],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  const formatter = new Intl.RelativeTimeFormat(getLocale(), { numeric: "auto" });
  for (const [unit, size] of ranges) {
    if (Math.abs(seconds) >= size) return formatter.format(Math.round(seconds / size), unit);
  }
  return formatter.format(seconds, "second");
}

export function shortPath(path: string | null | undefined): string {
  if (!path) return t("noProject");
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
  if (parts.length <= 2) return path;
  return "…/" + parts.slice(-2).join("/");
}

export async function copyText(text: string): Promise<void> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const field = document.createElement("textarea");
      field.value = text;
      field.setAttribute("readonly", "");
      field.className = "clipboard-field";
      document.body.appendChild(field);
      field.select();
      const copied = document.execCommand("copy");
      field.remove();
      if (!copied) throw new Error("copy failed");
    }
    return Promise.resolve();
  } catch (error) {
    return Promise.reject(error);
  }
}

export function isFoldable(text: string): boolean {
  return (text || "").length > 900 || (text || "").split("\n").length > 12;
}
