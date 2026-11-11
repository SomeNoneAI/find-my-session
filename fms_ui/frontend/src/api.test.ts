import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchJSON } from "@/api";
import { initAuth } from "@/auth";
import { t } from "@/i18n";

function stubFetch(impl: (url: string, init?: RequestInit) => Promise<unknown>): void {
  vi.stubGlobal("fetch", vi.fn(impl));
}

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: async () => body } as Response;
}

describe("fetchJSON", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
    window.history.replaceState(null, "", "/");
    initAuth();
  });

  it("sends the auth token header", async () => {
    window.history.replaceState(null, "", "/?token=abc123");
    initAuth();
    let captured: RequestInit | undefined;
    stubFetch(async (_url, init) => {
      captured = init;
      return jsonResponse({ harnesses: [] });
    });
    await fetchJSON("/api/harnesses");
    const headers = captured?.headers as Record<string, string>;
    expect(headers["X-FMS-Token"]).toBe("abc123");
    expect(headers.Accept).toBe("application/json");
  });

  it("maps 401 to the unauthorized message", async () => {
    stubFetch(async () => jsonResponse({ error: "unauthorized" }, false, 401));
    await expect(fetchJSON("/api/harnesses")).rejects.toThrow(t("unauthorized"));
  });

  it("surfaces the server error message", async () => {
    stubFetch(async () => jsonResponse({ error: "bad limit" }, false, 400));
    await expect(fetchJSON("/api/sessions")).rejects.toThrow("bad limit");
  });

  it("falls back to a status message when the error body has no message", async () => {
    stubFetch(async () => jsonResponse({}, false, 500));
    await expect(fetchJSON("/api/sessions")).rejects.toThrow(
      t("requestFailed", { status: 500 }),
    );
  });

  it("maps network failure to localServiceUnavailable", async () => {
    stubFetch(async () => {
      throw new TypeError("failed to fetch");
    });
    await expect(fetchJSON("/api/harnesses")).rejects.toThrow(
      t("localServiceUnavailable"),
    );
  });

  it("rethrows abort errors untouched", async () => {
    const abort = new Error("aborted");
    abort.name = "AbortError";
    stubFetch(async () => {
      throw abort;
    });
    await expect(fetchJSON("/api/harnesses")).rejects.toBe(abort);
  });

  it("maps invalid JSON to invalidResponse", async () => {
    stubFetch(async () => ({
      ok: true,
      status: 200,
      json: async () => {
        throw new SyntaxError("bad json");
      },
    }) as unknown as Response);
    await expect(fetchJSON("/api/harnesses")).rejects.toThrow(t("invalidResponse"));
  });
});