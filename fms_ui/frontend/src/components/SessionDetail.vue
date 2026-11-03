<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";

import { t } from "@/i18n";
import type {
  DetailTab,
  DetailView,
  PromptListingDTO,
  SessionDetailDTO,
  TodoDTO,
  ToolCallDTO,
} from "@/types";
import { copyText, formatDate } from "@/utils";
import { useToast } from "@/composables/useToast";

import PromptListing from "./PromptListing.vue";
import ProseBlock from "./ProseBlock.vue";

const props = defineProps<{
  view: DetailView;
  detail: SessionDetailDTO | null;
  detailError: string;
  tab: DetailTab;
  prompts: PromptListingDTO | null;
  promptLoading: boolean;
  promptError: string;
  promptOrder: "oldest" | "newest";
}>();

const emit = defineEmits<{
  selectTab: [tab: DetailTab];
  "update:promptOrder": [order: "oldest" | "newest"];
  pagePrompts: [direction: 1 | -1];
}>();

const { showToast } = useToast();
const pane = ref<HTMLElement | null>(null);

const tabs: Array<{ id: DetailTab; label: string }> = [
  { id: "overview", label: "overview" },
  { id: "prompts", label: "userPrompts" },
  { id: "recent", label: "recentTurns" },
];

const detailTitle = computed(() => {
  if (props.detailError) return t("sessionReadFailed");
  const detail = props.detail;
  if (!detail) return "";
  return detail.title || detail.first_prompt || t("unnamedSession");
});

const openStatuses = new Set(["pending", "in_progress", "processing", "blocked"]);

const sortedTodos = computed<TodoDTO[]>(() => {
  const todos = props.detail?.todos || [];
  return [...todos].sort((a, b) => {
    const aOpen = openStatuses.has(a.status || "") ? 0 : 1;
    const bOpen = openStatuses.has(b.status || "") ? 0 : 1;
    return aOpen - bOpen;
  });
});

const showOverview = computed(() => {
  const detail = props.detail;
  if (!detail) return false;
  return Boolean(
    detail.first_prompt ||
      (detail.last_prompt && detail.last_prompt !== detail.first_prompt) ||
      detail.compact_summary ||
      detail.todos.length ||
      detail.edited_files.length ||
      detail.recent_tools.length,
  );
});

function exchangeTools(tools: ToolCallDTO[]): string {
  if (!tools.length) return "";
  const counts = new Map<string, number>();
  for (const tool of tools) counts.set(tool.name, (counts.get(tool.name) || 0) + 1);
  return [...counts.entries()].map(([name, count]) => `${name} ×${count}`).join(" · ");
}

function onTabKeydown(event: KeyboardEvent): void {
  const currentIndex = tabs.findIndex((item) => item.id === props.tab);
  let nextIndex: number | null = null;
  if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length;
  if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
  if (event.key === "Home") nextIndex = 0;
  if (event.key === "End") nextIndex = tabs.length - 1;
  if (nextIndex !== null) {
    event.preventDefault();
    const next = tabs[nextIndex].id;
    emit("selectTab", next);
    document.getElementById(`tab-${next}`)?.focus();
  }
}

async function copyRef(): Promise<void> {
  if (!props.detail) return;
  try {
    await copyText(props.detail.ref);
    showToast(t("copiedRef"));
  } catch (error) {
    showToast(t("copyFailed"), { sticky: true });
  }
}

async function copyPath(): Promise<void> {
  if (!props.detail) return;
  try {
    await copyText(props.detail.path);
    showToast(t("copiedPath"));
  } catch (error) {
    showToast(t("copyFailed"), { sticky: true });
  }
}

watch(
  () => props.view,
  (view) => {
    if (view === "content") {
      void nextTick(() => pane.value?.scrollTo({ top: 0 }));
    }
  },
);
</script>

<template>
  <section ref="pane" class="detail-pane" :aria-label="t('sessionDetail')">
    <div v-if="view === 'empty'" class="detail-empty">
      <div class="section-kicker"><span>02</span> <span>{{ t("restoreContext") }}</span></div>
      <h1><span>{{ t("emptyHeadline") }}</span><br><em>{{ t("emptyHeadlineAccent") }}</em></h1>
      <p>{{ t("emptyDescription") }}</p>
      <div class="empty-hint"><span class="hint-line"></span><span>{{ t("selectSessionHint") }}</span></div>
    </div>

    <div v-else-if="view === 'loading'" class="detail-loading">
      <span class="loading-rule"></span>
      <p>{{ t("loadingDetail") }}</p>
    </div>

    <article v-else class="detail-content">
      <header class="detail-header">
        <div class="detail-eyebrow">
          <span class="harness-label">{{ detailError ? "ERROR" : detail?.harness }}</span>
          <span v-if="!detailError && detail?.archived" class="archived-label">{{ t("archivedBadge") }}</span>
        </div>
        <h1>{{ detailTitle }}</h1>
        <dl class="session-facts">
          <div>
            <dt>{{ t("factUpdated") }}</dt>
            <dd>{{ detail ? formatDate(detail.updated) : "" }}</dd>
          </div>
          <div>
            <dt>{{ t("factProject") }}</dt>
            <dd :title="detail?.cwd || ''">{{ detail?.cwd || t("noProject") }}</dd>
          </div>
          <div v-if="detail?.branch">
            <dt>{{ t("factBranch") }}</dt>
            <dd :title="detail.branch">{{ detail.branch }}</dd>
          </div>
          <div v-if="detail?.model">
            <dt>{{ t("factModel") }}</dt>
            <dd :title="detail.model">{{ detail.model }}</dd>
          </div>
        </dl>
        <div class="detail-actions">
          <button class="text-button" type="button" @click="copyRef">{{ t("copyRef") }}</button>
          <button class="text-button" type="button" @click="copyPath">{{ t("copyPath") }}</button>
        </div>
      </header>

      <nav class="detail-tabs" role="tablist" :aria-label="t('detailTabs')" @keydown="onTabKeydown">
        <button
          v-for="item in tabs"
          :id="`tab-${item.id}`"
          :key="item.id"
          class="detail-tab"
          :class="{ active: tab === item.id }"
          type="button"
          role="tab"
          :aria-selected="tab === item.id ? 'true' : 'false'"
          aria-controls="detail-panel"
          :tabindex="tab === item.id ? 0 : -1"
          @click="emit('selectTab', item.id)"
        >
          {{ t(item.label) }}
        </button>
      </nav>

      <div id="detail-panel" class="detail-panel" role="tabpanel" tabindex="0" :aria-labelledby="`tab-${tab}`">
        <div v-if="detailError" class="inline-error">{{ detailError }}</div>
        <template v-else-if="detail">
          <div v-if="tab === 'overview'">
            <p v-if="!showOverview" class="muted-note">{{ t("noOverview") }}</p>
            <section v-if="detail.first_prompt" class="content-section">
              <h2 class="content-heading">{{ t("task") }}</h2>
              <ProseBlock :text="detail.first_prompt" style-class="task-block" />
            </section>
            <section
              v-if="detail.last_prompt && detail.last_prompt !== detail.first_prompt"
              class="content-section"
            >
              <h2 class="content-heading">{{ t("latestRequest") }}</h2>
              <ProseBlock :text="detail.last_prompt" />
            </section>
            <section v-if="detail.compact_summary" class="content-section">
              <h2 class="content-heading">{{ t("compactSummary") }}</h2>
              <ProseBlock :text="detail.compact_summary" style-class="summary-block" />
            </section>
            <div v-if="detail.todos.length || detail.edited_files.length" class="overview-columns">
              <section v-if="detail.todos.length" class="content-section">
                <h2 class="content-heading">{{ t("todos", { count: detail.todos.length }) }}</h2>
                <ul class="todo-list">
                  <li v-for="(todo, index) in sortedTodos" :key="index" class="todo-item">
                    <span
                      class="todo-status"
                      :class="{ completed: !openStatuses.has(todo.status || '') }"
                    >{{ todo.status || "open" }}</span>
                    <span>{{ todo.subject || todo.content || t("unnamedTodo") }}</span>
                  </li>
                </ul>
              </section>
              <section v-if="detail.edited_files.length" class="content-section">
                <h2 class="content-heading">{{ t("editedFiles") }}</h2>
                <ul class="file-list">
                  <li v-for="(file, index) in detail.edited_files" :key="index" class="file-item">
                    <span class="file-path" :title="file.path || ''">{{ file.path || t("unknownPath") }}</span>
                    <span v-if="(file.count || 1) > 1" class="file-count">×{{ file.count }}</span>
                  </li>
                </ul>
              </section>
            </div>
            <section v-if="detail.recent_tools.length" class="content-section">
              <h2 class="content-heading">{{ t("recentTools") }}</h2>
              <ul class="tool-list">
                <li v-for="(tool, index) in [...detail.recent_tools].reverse()" :key="index" class="tool-item">
                  <div class="tool-name">{{ tool.name }}</div>
                  <div v-if="tool.detail" class="tool-detail">{{ tool.detail }}</div>
                </li>
              </ul>
            </section>
          </div>

          <PromptListing
            v-else-if="tab === 'prompts'"
            :listing="prompts"
            :loading="promptLoading"
            :error="promptError"
            :order="promptOrder"
            @update:order="emit('update:promptOrder', $event)"
            @page="emit('pagePrompts', $event)"
          />

          <div v-else>
            <p v-if="!detail.exchanges.length" class="muted-note">{{ t("noRecentTurns") }}</p>
            <article v-for="(exchange, index) in detail.exchanges" :key="index" class="exchange exchange-user">
              <template v-if="exchange.user">
                <h2 class="exchange-label">
                  {{ t("roleUser") }}
                  <time>{{ formatDate(exchange.timestamp) }}</time>
                </h2>
                <ProseBlock :text="exchange.user" />
              </template>
              <div v-if="exchange.assistant.length" class="exchange-assistant">
                <h2 class="exchange-label">{{ t("roleAssistant") }}</h2>
                <ProseBlock v-for="(text, ai) in exchange.assistant" :key="ai" :text="text" />
              </div>
              <div v-if="exchangeTools(exchange.tools)" class="exchange-tools">
                {{ exchangeTools(exchange.tools) }}
              </div>
            </article>
          </div>
        </template>
      </div>
    </article>
  </section>
</template>
