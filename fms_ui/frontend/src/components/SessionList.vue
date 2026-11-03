<script setup lang="ts">
import { t } from "@/i18n";
import type { SearchStatus, SessionSummaryDTO } from "@/types";
import { formatDate, relativeDate, shortPath } from "@/utils";

defineProps<{
  sessions: SessionSummaryDTO[];
  selectedRef: string | null;
  compact: boolean;
  status: SearchStatus;
}>();

const emit = defineEmits<{
  select: [ref: string];
}>();

function sessionTitle(session: SessionSummaryDTO): string {
  return session.title || session.first_prompt || t("unnamedSession");
}

function sessionAriaLabel(session: SessionSummaryDTO): string {
  return t("sessionAriaLabel", {
    title: sessionTitle(session),
    harness: session.harness,
    time: relativeDate(session.updated),
  });
}
</script>

<template>
  <div class="results-region">
    <ol
      v-if="status === 'searching'"
      class="session-list"
      :class="{ compact: compact }"
      :aria-label="t('sessionResults')"
    >
      <li v-for="index in 5" :key="index" class="skeleton-row">
        <div class="skeleton-line short"></div>
        <div class="skeleton-line"></div>
        <div class="skeleton-line medium"></div>
      </li>
    </ol>
    <template v-else>
      <ol class="session-list" :class="{ compact: compact }" :aria-label="t('sessionResults')">
        <li
          v-for="session in sessions"
          :key="session.ref"
          class="session-item"
          :class="{ selected: session.ref === selectedRef }"
        >
          <button
            class="session-button"
            type="button"
            :aria-label="sessionAriaLabel(session)"
            @click="emit('select', session.ref)"
          >
            <span v-if="compact" class="session-compact-line">
              <span class="session-title-compact">{{ sessionTitle(session) }}</span>
              <time
                class="session-time"
                :datetime="session.updated || ''"
                :title="formatDate(session.updated)"
              >{{ relativeDate(session.updated) }}</time>
            </span>
            <template v-else>
              <span class="session-topline">
                <span class="session-harness">{{ session.harness }}</span>
                <span v-if="session.archived" class="session-archived">{{ t("archivedTag") }}</span>
                <time
                  class="session-time"
                  :datetime="session.updated || ''"
                  :title="formatDate(session.updated)"
                >{{ relativeDate(session.updated) }}</time>
              </span>
              <h2 class="session-title">{{ sessionTitle(session) }}</h2>
              <span class="session-cwd" :title="session.cwd || ''">{{ shortPath(session.cwd) }}</span>
            </template>
          </button>
        </li>
      </ol>
      <div v-if="!sessions.length" class="results-empty">
        <h2>{{ t("noSessionsTitle") }}</h2>
        <p>{{ t("noSessionsDescription") }}</p>
      </div>
    </template>
  </div>
</template>
