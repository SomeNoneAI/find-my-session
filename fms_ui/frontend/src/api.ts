import { t } from "@/i18n";
import type { HarnessListResponse, ProjectListResponse, PromptListingDTO, SessionDetailDTO, SessionListResponse, StatsResponseDTO } from "@/types";
import { isAbortError } from "@/utils";

export class ApiError extends Error {}

export async function fetchJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { signal, headers: { Accept: "application/json" } });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError(t("localServiceUnavailable"));
  }
  let data: unknown;
  try {
    data = await response.json();
  } catch (error) {
    throw new ApiError(t("invalidResponse"));
  }
  if (!response.ok) {
    const message =
      data && typeof data === "object" && "error" in data
        ? String((data as { error: unknown }).error)
        : t("requestFailed", { status: response.status });
    throw new ApiError(message);
  }
  return data as T;
}

export function fetchHarnesses(signal?: AbortSignal): Promise<HarnessListResponse> {
  return fetchJSON<HarnessListResponse>("/api/harnesses", signal);
}

export function fetchSessions(
  params: string,
  signal?: AbortSignal,
): Promise<SessionListResponse> {
  return fetchJSON<SessionListResponse>(`/api/sessions?${params}`, signal);
}

export function fetchSessionDetail(
  ref: string,
  signal?: AbortSignal,
): Promise<SessionDetailDTO> {
  const params = new URLSearchParams({ ref, messages: "20" });
  return fetchJSON<SessionDetailDTO>(`/api/session?${params.toString()}`, signal);
}

export function fetchPrompts(params: {
  ref: string;
  offset: number;
  limit: number;
  order: string;
  signal?: AbortSignal;
}): Promise<PromptListingDTO> {
  const search = new URLSearchParams({
    ref: params.ref,
    offset: String(params.offset),
    limit: String(params.limit),
    order: params.order,
  });
  return fetchJSON<PromptListingDTO>(`/api/prompts?${search.toString()}`, params.signal);
}

export function fetchStats(signal?: AbortSignal): Promise<StatsResponseDTO> {
  return fetchJSON<StatsResponseDTO>("/api/stats", signal);
}

export function fetchProjects(
  filters: { harness: string; archived: boolean },
  signal?: AbortSignal,
): Promise<ProjectListResponse> {
  const params = new URLSearchParams();
  if (filters.harness) params.set("harness", filters.harness);
  if (filters.archived) params.set("archived", "true");
  return fetchJSON<ProjectListResponse>(`/api/projects?${params.toString()}`, signal);
}
