<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { isFoldable } from "@/utils";
import { t } from "@/i18n";

const props = defineProps<{
  text: string;
  styleClass?: string;
}>();

const expanded = ref(false);
const foldable = computed(() => isFoldable(props.text));

// A reused block shows a different prompt/summary: start collapsed again,
// matching the old implementation that rebuilt the DOM for each render.
watch(
  () => props.text,
  () => {
    expanded.value = false;
  },
);
</script>

<template>
  <div
    class="prose-block"
    :class="[styleClass, { foldable: foldable && !expanded, expanded: expanded }]"
  >
    <pre class="prose-text">{{ text }}</pre>
    <button v-if="foldable" class="fold-button" type="button" @click="expanded = !expanded">
      {{ expanded ? t("showLess") : t("showMore") }}
    </button>
  </div>
</template>
