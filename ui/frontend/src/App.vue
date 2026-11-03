<script setup lang="ts">
import { onMounted, ref, watchEffect } from "vue";

import { getLocale, locales, setLocale, t } from "@/i18n";
import { useTheme } from "@/composables/useTheme";
import { useWorkspace } from "@/composables/useWorkspace";
import { readStoredFlag, writeStoredFlag } from "@/utils";

import SearchFilters from "@/components/SearchFilters.vue";
import SessionDetail from "@/components/SessionDetail.vue";
import SessionList from "@/components/SessionList.vue";
import Toast from "@/components/Toast.vue";

const store = useWorkspace();
const { theme, themeToggleLabel, toggleTheme } = useTheme();

const compact = ref(readStoredFlag("fms-ui-compact"));
const language = ref(getLocale());
const searchFilters = ref<{ closeAutocomplete: () => void; refreshAutocomplete: () => void } | null>(
  null,
);

watchEffect(() => {
  document.title = t("localPanelTitle");
});

function setCompact(value: boolean): void {
  compact.value = value;
  writeStoredFlag("fms-ui-compact", value);
}

function runSearch(): void {
  searchFilters.value?.closeAutocomplete();
  void store.searchSessions();
}

function onFilterChanged(field: "harness" | "archived" | "since" | "deep"): void {
  if (field === "harness" || field === "archived") {
    searchFilters.value?.refreshAutocomplete();
  }
  runSearch();
}

function rescan(): void {
  searchFilters.value?.refreshAutocomplete();
  runSearchWithRefresh();
}

function runSearchWithRefresh(): void {
  searchFilters.value?.closeAutocomplete();
  void store.searchSessions({ refresh: true });
}

function onLanguageChange(): void {
  setLocale(language.value);
}

onMounted(() => {
  void Promise.all([store.loadHarnesses(), store.searchSessions()]);
});
</script>

<template>
  <div class="app-shell">
    <header class="masthead">
      <a class="brand" href="/" :aria-label="t('brandHome')">
        <img class="brand-mark" src="/favicon.svg" alt="" width="30" height="30">
        <span class="brand-name">Find My Session</span>
      </a>
      <div class="masthead-meta">
        <button
          id="compact-toggle"
          class="mode-toggle"
          :class="{ active: compact }"
          type="button"
          :aria-pressed="compact ? 'true' : 'false'"
          @click="setCompact(!compact)"
        >
          {{ t("compactMode") }}
        </button>
        <select
          id="language-select"
          v-model="language"
          class="language-select"
          :aria-label="t('language')"
          @change="onLanguageChange"
        >
          <option v-for="item in locales" :key="item.code" :value="item.code">
            {{ item.label }}
          </option>
        </select>
      </div>
    </header>

    <main class="workspace">
      <aside class="browser-pane" :aria-label="t('sessionSearch')">
        <SearchFilters
          ref="searchFilters"
          :filters="store.filters"
          :harness-options="store.harnessOptions"
          :refresh-loading="store.refreshLoading"
          :theme-toggle-label="themeToggleLabel"
          :theme-dark="theme === 'dark'"
          @submit-search="runSearch"
          @rescan="rescan"
          @filter-changed="onFilterChanged"
          @toggle-theme="toggleTheme"
        />

        <div class="results-heading">
          <span id="results-status" role="status">{{ store.resultsLabel }}</span>
        </div>

        <SessionList
          :sessions="store.sessions"
          :selected-ref="store.selectedRef"
          :compact="compact"
          :status="store.searchStatus"
          @select="store.loadSession"
        />
      </aside>

      <SessionDetail
        :view="store.detailView"
        :detail="store.detail"
        :detail-error="store.detailError"
        :tab="store.tab"
        :prompts="store.prompts"
        :prompt-loading="store.promptLoading"
        :prompt-error="store.promptError"
        :prompt-order="store.promptOrder"
        @select-tab="store.selectTab"
        @update:prompt-order="store.setPromptOrder"
        @page-prompts="store.pagePrompts"
      />
    </main>
  </div>
  <Toast />
</template>
