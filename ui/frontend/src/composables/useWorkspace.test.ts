import { beforeEach, describe, expect, it, vi } from "vitest";

import { useWorkspace } from "@/composables/useWorkspace";
import { detailFor, flush, stubFetch, summary } from "@/testing/fixtures";

beforeEach(() => {
  window.localStorage.clear();
});

describe("useWorkspace search coordination", () => {
  it("sends all active filters and omits empty ones", async () => {
    const { calls } = stubFetch((url) => {
      if (url.startsWith("/api/sessions")) {
        return { sessions: [], revision: 1, refreshing: false };
      }
      return {};
    });

    const store = useWorkspace();
    await store.searchSessions();
    const initial = new URLSearchParams(calls[0].split("?")[1]);
    expect(calls[0]).toContain("/api/sessions?");
    expect(initial.get("limit")).toBe("50");
    expect([...initial.keys()].sort()).toEqual(["limit"]);

    store.filters.query = "dark mode";
    store.filters.harness = "qoder-cn";
    store.filters.cwd = "/Users/example/app";
    store.filters.since = "7d";
    store.filters.archived = true;
    store.filters.deep = true;
    await store.searchSessions();
    const params = new URLSearchParams(calls[1].split("?")[1]);
    expect(params.get("query")).toBe("dark mode");
    expect(params.get("harness")).toBe("qoder-cn");
    expect(params.get("cwd")).toBe("/Users/example/app");
    expect(params.get("since")).toBe("7d");
    expect(params.get("archived")).toBe("true");
    expect(params.get("deep")).toBe("true");
    expect(params.get("limit")).toBe("50");
  });

  it("keeps the current detail without refetching when the selection survives a search", async () => {
    const first = summary("qoder-cn:aaaaaaaa");
    const detailCalls: string[] = [];
    stubFetch((url) => {
      if (url.startsWith("/api/sessions")) {
        return { sessions: [first], revision: 1, refreshing: false };
      }
      if (url.startsWith("/api/session?")) {
        detailCalls.push(url);
        return detailFor(first.ref);
      }
      return {};
    });

    const store = useWorkspace();
    await store.searchSessions();
    await flush();
    await flush();
    expect(store.selectedRef).toBe(first.ref);
    expect(store.detail?.ref).toBe(first.ref);
    expect(detailCalls).toHaveLength(1);

    await store.searchSessions();
    await flush();
    expect(detailCalls).toHaveLength(1);
    expect(store.detail?.ref).toBe(first.ref);
    expect(store.detailView).toBe("content");
  });

  it("manual refresh serves the old snapshot then adopts the new revision", async () => {
    const before = [summary("qoder-cn:aaaaaaaa")];
    const after = [
      summary("qoder-cn:aaaaaaaa"),
      summary("qoder-cn:bbbbbbbb", "/Users/example/other"),
    ];
    const { calls } = stubFetch((url) => {
      if (url.startsWith("/api/session?")) return detailFor(before[0].ref);
      if (url.includes("refresh=true")) {
        return { sessions: before, revision: 1, refreshing: true };
      }
      if (url.includes("wait=true")) {
        return { sessions: after, revision: 2, refreshing: false };
      }
      return { sessions: before, revision: 1, refreshing: false };
    });

    const store = useWorkspace();
    await store.searchSessions();
    await flush();
    expect(store.sessions).toHaveLength(1);
    expect(store.revision).toBe(1);

    await store.searchSessions({ refresh: true });

    const refreshCall = calls.find((url) => url.includes("refresh=true"));
    expect(refreshCall).toBeDefined();
    const waitCall = calls.find((url) => url.includes("wait=true"));
    expect(waitCall).toBeDefined();
    expect(new URLSearchParams(waitCall!.split("?")[1]).get("revision")).toBe("1");
    expect(calls.indexOf(refreshCall!)).toBeLessThan(calls.indexOf(waitCall!));

    expect(store.sessions).toHaveLength(2);
    expect(store.revision).toBe(2);
    expect(store.searchStatus).toBe("done");
    expect(store.refreshLoading).toBe(false);
  });

  it("surfaces scan failures as an error state without sessions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 500,
        json: async () => ({ error: "cannot scan session stores: boom" }),
      })) as unknown as typeof fetch,
    );

    const store = useWorkspace();
    await store.searchSessions();
    expect(store.searchStatus).toBe("error");
    expect(store.sessions).toEqual([]);
  });
});
