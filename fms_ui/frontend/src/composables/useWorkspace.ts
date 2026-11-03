import { computed, reactive, ref } from "vue";

import * as api from "@/api";
import { t } from "@/i18n";
import type {
  DetailTab,
  DetailView,
  HarnessRow,
  PromptListingDTO,
  SearchFilters,
  SearchStatus,
  SessionDetailDTO,
  SessionListResponse,
  SessionSummaryDTO,
} from "@/types";
import { isAbortError, queryString } from "@/utils";

import { useToast } from "./useToast";

const SEARCH_LIMIT = 50;
const PROMPT_LIMIT = 20;
const POLL_ATTEMPTS = 12;

export function useWorkspace() {
  const { showToast } = useToast();

  const filters = reactive<SearchFilters>({
    query: "",
    harness: "",
    cwd: "",
    since: "",
    archived: false,
    deep: false,
  });

  const sessions = ref<SessionSummaryDTO[]>([]);
  const selectedRef = ref<string | null>(null);
  const detail = ref<SessionDetailDTO | null>(null);
  const detailError = ref("");
  const tab = ref<DetailTab>("overview");
  const prompts = ref<PromptListingDTO | null>(null);
  const promptOffset = ref(0);
  const promptOrder = ref<"oldest" | "newest">("oldest");
  const promptLoading = ref(false);
  const promptError = ref("");
  const searchStatus = ref<SearchStatus>("ready");
  const revision = ref<number | null>(null);
  const refreshLoading = ref(false);
  const harnessOptions = ref<HarnessRow[]>([]);

  let searchController: AbortController | null = null;
  let detailController: AbortController | null = null;
  let promptController: AbortController | null = null;
  let pollController: AbortController | null = null;
  let pollEpoch = 0;

  const detailView = computed<DetailView>(() => {
    if (!selectedRef.value) return "empty";
    if (!detail.value && !detailError.value) return "loading";
    return "content";
  });

  const resultsLabel = computed(() => {
    if (searchStatus.value === "ready") return t("readyToScan");
    if (searchStatus.value === "searching" || searchStatus.value === "refreshing") {
      return t(filters.deep ? "scanningDeep" : "scanning");
    }
    if (searchStatus.value === "error") return t("scanFailed");
    return t("sessionCount", {
      count: sessions.value.length,
      mode: t(filters.deep ? "fullTextSearch" : "metadataSearch"),
    });
  });

  function searchParams(): Record<string, string | number | boolean> {
    return {
      query: filters.query.trim(),
      harness: filters.harness,
      cwd: filters.cwd.trim(),
      since: filters.since,
      archived: filters.archived,
      deep: filters.deep,
      limit: SEARCH_LIMIT,
    };
  }

  function adoptSessions(data: SessionListResponse): void {
    sessions.value = data.sessions;
    if (typeof data.revision === "number") revision.value = data.revision;
    searchStatus.value = "done";
    if (!sessions.value.length) {
      selectedRef.value = null;
      detail.value = null;
      detailError.value = "";
      return;
    }
    const retained = sessions.value.find((session) => session.ref === selectedRef.value);
    const nextRef = (retained || sessions.value[0]).ref;
    if (nextRef === selectedRef.value && detail.value) return;
    void loadSession(nextRef);
  }

  async function waitForSnapshot(epoch: number): Promise<void> {
    const baseline = revision.value;
    for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt += 1) {
      if (epoch !== pollEpoch) return;
      const controller = new AbortController();
      pollController = controller;
      let data: SessionListResponse;
      try {
        const params = queryString({ ...searchParams(), revision: baseline, wait: true });
        data = await api.fetchSessions(params, controller.signal);
      } catch (error) {
        return;
      } finally {
        if (pollController === controller) pollController = null;
      }
      if (epoch !== pollEpoch) return;
      if (data.revision !== baseline) {
        adoptSessions(data);
        return;
      }
      if (!data.refreshing) return;
    }
  }

  async function searchSessions(options: { refresh?: boolean } = {}): Promise<void> {
    const refresh = options.refresh === true;
    pollEpoch += 1;
    const epoch = pollEpoch;
    if (searchController) searchController.abort();
    if (detailController) detailController.abort();
    if (promptController) promptController.abort();
    if (pollController) pollController.abort();
    const controller = new AbortController();
    searchController = controller;
    searchStatus.value = refresh ? "refreshing" : "searching";
    refreshLoading.value = true;
    try {
      const params = searchParams();
      if (refresh) params.refresh = true;
      const data = await api.fetchSessions(queryString(params), controller.signal);
      if (searchController !== controller) return;
      adoptSessions(data);
      if (refresh && data.refreshing && data.revision === revision.value) {
        searchStatus.value = "refreshing";
        await waitForSnapshot(epoch);
        if (epoch === pollEpoch && searchStatus.value === "refreshing") {
          searchStatus.value = "done";
        }
      }
    } catch (error) {
      if (isAbortError(error)) return;
      sessions.value = [];
      searchStatus.value = "error";
      showToast(error instanceof Error ? error.message : t("scanFailed"), { sticky: true });
    } finally {
      if (searchController === controller) {
        searchController = null;
        if (!refresh || searchStatus.value !== "refreshing") {
          refreshLoading.value = false;
        }
      }
    }
  }

  async function loadSession(ref: string): Promise<void> {
    if (!ref) return;
    if (detailController) detailController.abort();
    if (promptController) promptController.abort();
    const controller = new AbortController();
    detailController = controller;
    selectedRef.value = ref;
    detail.value = null;
    detailError.value = "";
    prompts.value = null;
    promptOffset.value = 0;
    promptError.value = "";
    tab.value = "overview";
    try {
      const data = await api.fetchSessionDetail(ref, controller.signal);
      if (selectedRef.value !== ref) return;
      detail.value = data;
    } catch (error) {
      if (isAbortError(error)) return;
      detailError.value = error instanceof Error ? error.message : t("sessionReadFailed");
    } finally {
      if (detailController === controller) detailController = null;
    }
  }

  async function loadPrompts(): Promise<void> {
    if (!selectedRef.value) return;
    if (promptController) promptController.abort();
    const controller = new AbortController();
    promptController = controller;
    const ref = selectedRef.value;
    prompts.value = null;
    promptError.value = "";
    promptLoading.value = true;
    try {
      const listing = await api.fetchPrompts({
        ref,
        offset: promptOffset.value,
        limit: PROMPT_LIMIT,
        order: promptOrder.value,
        signal: controller.signal,
      });
      if (selectedRef.value !== ref) return;
      prompts.value = listing;
    } catch (error) {
      if (isAbortError(error)) return;
      promptError.value = error instanceof Error ? error.message : t("sessionReadFailed");
    } finally {
      promptLoading.value = false;
      if (promptController === controller) promptController = null;
    }
  }

  function selectTab(next: DetailTab): void {
    tab.value = next;
    if (!detail.value) return;
    if (next === "prompts") void loadPrompts();
  }

  function setPromptOrder(order: "oldest" | "newest"): void {
    promptOrder.value = order;
    promptOffset.value = 0;
    void loadPrompts();
  }

  function pagePrompts(direction: 1 | -1): void {
    promptOffset.value = Math.max(0, promptOffset.value + direction * PROMPT_LIMIT);
    void loadPrompts();
  }

  async function loadHarnesses(): Promise<void> {
    try {
      const data = await api.fetchHarnesses();
      harnessOptions.value = data.harnesses.filter((row) => row.status === "ready");
    } catch (error) {
      showToast(t("harnessesLoadFailed", { message: errorMessage(error) }), { sticky: true });
    }
  }

  return reactive({
    filters,
    sessions,
    selectedRef,
    detail,
    detailError,
    detailView,
    tab,
    prompts,
    promptOffset,
    promptOrder,
    promptLoading,
    promptError,
    searchStatus,
    resultsLabel,
    revision,
    refreshLoading,
    harnessOptions,
    searchSessions,
    loadSession,
    loadPrompts,
    selectTab,
    setPromptOrder,
    pagePrompts,
    loadHarnesses,
  });
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
