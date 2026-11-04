<script setup lang="ts">
import { onMounted, ref } from "vue";

import { fetchStats } from "@/api";
import { t } from "@/i18n";
import type { StatsRowDTO } from "@/types";

const emit = defineEmits<{ close: [] }>();

const rows = ref<StatsRowDTO[] | null>(null);
const loading = ref(true);
const error = ref("");

function formatNumber(value: number | null): string {
  return value === null ? "-" : value.toLocaleString();
}

function formatCost(value: number | null): string {
  return value === null ? "-" : value.toFixed(4);
}

function usageCell(row: StatsRowDTO, key: "tokens_input" | "tokens_output" | "tokens_cache_read" | "cost_usd"): string {
  if (row.sessions_with_usage === 0) return "-";
  if (key === "cost_usd") return formatCost(row[key]);
  return formatNumber(row[key]);
}

onMounted(async () => {
  try {
    const response = await fetchStats();
    rows.value = response.stats;
  } catch (cause) {
    error.value = t("statsLoadFailed", { message: String(cause) });
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="stats-overlay" role="dialog" :aria-label="t('statsTitle')">
    <section class="stats-panel">
      <header class="stats-header">
        <h2>{{ t("statsTitle") }}</h2>
        <button class="text-button" type="button" @click="emit('close')">
          {{ t("statsClose") }}
        </button>
      </header>
      <p v-if="loading" class="stats-loading">{{ t("statsLoading") }}</p>
      <p v-else-if="error" class="stats-error">{{ error }}</p>
      <p v-else-if="!rows || rows.length === 0" class="stats-loading">{{ t("statsEmpty") }}</p>
      <table v-else class="stats-table">
        <thead>
          <tr>
            <th scope="col">{{ t("agent") }}</th>
            <th scope="col">{{ t("statsSessions") }}</th>
            <th scope="col">{{ t("statsUsageSessions") }}</th>
            <th scope="col">{{ t("statsInputTokens") }}</th>
            <th scope="col">{{ t("statsOutputTokens") }}</th>
            <th scope="col">{{ t("statsCost") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.harness">
            <td>{{ row.harness }}</td>
            <td class="numeral">{{ row.sessions }}</td>
            <td class="numeral">{{ row.sessions_with_usage }}</td>
            <td class="numeral">{{ usageCell(row, "tokens_input") }}</td>
            <td class="numeral">{{ usageCell(row, "tokens_output") }}</td>
            <td class="numeral">{{ usageCell(row, "cost_usd") }}</td>
          </tr>
        </tbody>
      </table>
      <p
        v-if="rows && rows.some((row) => row.sessions_with_usage === 0)"
        class="stats-note"
      >
        {{ t("statsNotRecorded") }}
      </p>
    </section>
  </div>
</template>
