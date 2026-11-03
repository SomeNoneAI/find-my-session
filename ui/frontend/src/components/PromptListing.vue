<script setup lang="ts">
import { t } from "@/i18n";
import type { PromptListingDTO } from "@/types";
import { formatDate } from "@/utils";

import ProseBlock from "./ProseBlock.vue";

defineProps<{
  listing: PromptListingDTO | null;
  loading: boolean;
  error: string;
  order: "oldest" | "newest";
}>();

const emit = defineEmits<{
  "update:order": [order: "oldest" | "newest"];
  page: [direction: 1 | -1];
}>();
</script>

<template>
  <div>
    <div v-if="error" class="inline-error">{{ error }}</div>
    <p v-else-if="loading || !listing" class="muted-note">{{ t("loadingPrompts") }}</p>
    <template v-else>
      <div class="prompt-toolbar">
        <span class="prompt-total">{{ t("promptTotal", { count: listing.total }) }}</span>
        <select
          class="compact-select"
          :aria-label="t('promptOrderLabel')"
          :value="order"
          @change="emit('update:order', ($event.target as HTMLSelectElement).value as 'oldest' | 'newest')"
        >
          <option value="oldest">{{ t("oldestFirst") }}</option>
          <option value="newest">{{ t("newestFirst") }}</option>
        </select>
        <button
          class="page-button"
          type="button"
          :disabled="listing.offset === 0"
          @click="emit('page', -1)"
        >
          {{ t("previousPage") }}
        </button>
        <button
          class="page-button"
          type="button"
          :disabled="!listing.has_more"
          @click="emit('page', 1)"
        >
          {{ t("nextPage") }}
        </button>
      </div>
      <p v-if="!listing.prompts.length" class="muted-note">
        {{ listing.total ? t("noPromptsInPage") : t("noPrompts") }}
      </p>
      <ol v-else class="prompt-list">
        <li v-for="prompt in listing.prompts" :key="prompt.index" class="prompt-item">
          <span class="prompt-index">{{ String(prompt.index).padStart(2, "0") }}</span>
          <div class="prompt-content">
            <time class="prompt-time" :datetime="prompt.timestamp || ''">
              {{ formatDate(prompt.timestamp) }}
            </time>
            <ProseBlock :text="prompt.text" />
          </div>
        </li>
      </ol>
    </template>
  </div>
</template>
