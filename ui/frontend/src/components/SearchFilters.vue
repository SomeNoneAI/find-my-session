<script setup lang="ts">
import { ref } from "vue";

import { t } from "@/i18n";
import type { HarnessRow, SearchFilters } from "@/types";

import ProjectAutocomplete from "./ProjectAutocomplete.vue";

defineProps<{
  filters: SearchFilters;
  harnessOptions: HarnessRow[];
  refreshLoading: boolean;
  themeToggleLabel: string;
  themeDark: boolean;
}>();

const emit = defineEmits<{
  submitSearch: [];
  rescan: [];
  filterChanged: [field: "harness" | "archived" | "since" | "deep"];
  toggleTheme: [];
}>();

const projectAutocomplete = ref<InstanceType<typeof ProjectAutocomplete> | null>(null);

defineExpose({
  closeAutocomplete: () => projectAutocomplete.value?.close(),
  refreshAutocomplete: () => projectAutocomplete.value?.refresh(),
});

function onSubmit(event: Event): void {
  event.preventDefault();
  emit("submitSearch");
}
</script>

<template>
  <div class="search-deck">
    <div class="section-kicker"><span>01</span> <span>{{ t("searchArchive") }}</span></div>
    <form @submit="onSubmit">
      <label class="visually-hidden" for="query-input">{{ t("search") }}</label>
      <div class="search-field">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.8"></circle><path d="m16 16 5 5"></path></svg>
        <input
          id="query-input"
          v-model="filters.query"
          name="query"
          type="search"
          :placeholder="t('searchPlaceholder')"
          autocomplete="off"
        >
        <button class="search-submit" type="submit">{{ t("searchButton") }}</button>
      </div>

      <div class="filter-grid">
        <label class="filter-field">
          <span class="visually-hidden">{{ t("agent") }}</span>
          <select
            id="harness-select"
            v-model="filters.harness"
            name="harness"
            :aria-label="t('agent')"
            @change="emit('filterChanged', 'harness')"
          >
            <option value="">{{ t("allAgents") }}</option>
            <option
              v-for="row in harnessOptions"
              :key="row.name"
              :value="row.name"
              :title="`${row.variants} · ${row.store}`"
            >
              {{ row.name }}
            </option>
          </select>
        </label>
        <label class="filter-field">
          <span class="visually-hidden">{{ t("updatedTime") }}</span>
          <select
            id="since-select"
            v-model="filters.since"
            name="since"
            :aria-label="t('updatedTime')"
            @change="emit('filterChanged', 'since')"
          >
            <option value="">{{ t("anyTime") }}</option>
            <option value="24h">{{ t("last24Hours") }}</option>
            <option value="7d">{{ t("last7Days") }}</option>
            <option value="2w">{{ t("last2Weeks") }}</option>
          </select>
        </label>
      </div>

      <ProjectAutocomplete
        ref="projectAutocomplete"
        v-model="filters.cwd"
        :harness="filters.harness"
        :archived="filters.archived"
        @select="emit('submitSearch')"
      />

      <div class="search-options">
        <label class="check-option">
          <input v-model="filters.archived" type="checkbox" @change="emit('filterChanged', 'archived')">
          <span>{{ t("includeArchived") }}</span>
        </label>
        <label class="check-option">
          <input v-model="filters.deep" type="checkbox" @change="emit('filterChanged', 'deep')">
          <span><span>{{ t("deepSearch") }}</span> <small>{{ t("slower") }}</small></span>
        </label>
        <button
          class="icon-button theme-toggle"
          type="button"
          :aria-pressed="themeDark ? 'true' : 'false'"
          :aria-label="themeToggleLabel"
          :title="themeToggleLabel"
          @click="emit('toggleTheme')"
        >
          <svg class="theme-icon theme-icon-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path></svg>
          <svg class="theme-icon theme-icon-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 13.5A8 8 0 0 1 10.5 4 8 8 0 1 0 20 13.5Z"></path></svg>
        </button>
        <button
          id="refresh-button"
          class="icon-button"
          :class="{ loading: refreshLoading }"
          type="button"
          :title="t('rescan')"
          :aria-label="t('rescan')"
          @click="emit('rescan')"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 7v5h-5"></path><path d="M18.5 16a8 8 0 1 1 1.2-7L20 12"></path></svg>
        </button>
      </div>
    </form>
  </div>
</template>
