<script setup lang="ts">
import { t } from "@/i18n";
import { useToast } from "@/composables/useToast";

const { toast, hideToast } = useToast();
</script>

<template>
  <div
    class="toast"
    :class="{ visible: toast.visible, sticky: toast.sticky }"
    role="status"
    aria-live="polite"
  >
    <span class="toast-message">{{ toast.message }}</span>
    <button
      v-if="toast.sticky"
      class="toast-close"
      type="button"
      :aria-label="t('dismiss')"
      @click="hideToast"
    >
      {{ t("dismiss") }}
    </button>
  </div>
</template>
