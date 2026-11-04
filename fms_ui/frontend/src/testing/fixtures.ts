import { vi } from "vitest";

import type { SessionDetailDTO, SessionSummaryDTO } from "@/types";

export function summary(ref: string, cwd = "/Users/example/app"): SessionSummaryDTO {
  return {
    ref,
    harness: ref.split(":")[0],
    session_id: ref.split(":")[1] + "-0000-4000-8000-000000000000",
    path: "/store/" + ref.split(":")[1] + ".jsonl",
    cwd,
    title: "session " + ref,
    first_prompt: "first prompt for " + ref,
    last_prompt: "last prompt for " + ref,
    started: "2026-10-01T09:00:00.000Z",
    updated: "2026-10-20T09:00:05.000Z",
    branch: "main",
    model: "test-model",
    entrypoint: "",
    version: "",
    size_bytes: 1024,
    variants: "desktop",
    archived: false,
  };
}

export function detailFor(ref: string): SessionDetailDTO {
  return {
    ...summary(ref),
    compact_summary: "",
    todos: [],
    turn_count: 1,
    exchanges: [],
    edited_files: [],
    tool_counts: {},
    resume_argv: null,
    recent_tools: [],
  };
}

type Handler = (url: string) => unknown;

export function stubFetch(handler: Handler): { calls: string[] } {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      const data = handler(url);
      return { ok: true, json: async () => data } as Response;
    }),
  );
  return { calls };
}

export function flush(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}
