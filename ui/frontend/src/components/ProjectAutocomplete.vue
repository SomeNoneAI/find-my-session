<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { fetchProjects } from "@/api";
import { t } from "@/i18n";

const props = defineProps<{
  modelValue: string;
  harness: string;
  archived: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
  select: [];
}>();

const input = ref<HTMLInputElement | null>(null);
const toggle = ref<HTMLButtonElement | null>(null);
const list = ref<HTMLUListElement | null>(null);
const isOpen = ref(false);
const projects = ref<string[]>([]);
const activeIndex = ref(-1);
const message = ref("");
const query = ref("");

const cache = new Map<string, string[]>();
let loadingController: AbortController | null = null;
let requestNumber = 0;

const filtered = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase();
  return projects.value.filter((path) => path.toLocaleLowerCase().includes(needle));
});

// Keep the filter term in sync with the bound cwd value (select() and the
// parent's v-model both write it from outside).
watch(
  () => props.modelValue,
  (value) => {
    query.value = value;
  },
  { immediate: true },
);

const activeDescendant = computed(() =>
  isOpen.value && activeIndex.value >= 0 ? `project-option-${activeIndex.value}` : undefined,
);

function close(): void {
  isOpen.value = false;
  activeIndex.value = -1;
}

function select(path: string): void {
  emit("update:modelValue", path);
  query.value = path;
  close();
  emit("select");
}

function setActive(index: number): void {
  if (!filtered.value.length) {
    activeIndex.value = -1;
    return;
  }
  const count = filtered.value.length;
  activeIndex.value = (index + count) % count;
  const option = list.value?.querySelectorAll(".project-option button")[activeIndex.value];
  if (option instanceof HTMLElement && typeof option.scrollIntoView === "function") {
    option.scrollIntoView({ block: "nearest" });
  }
}

async function load(): Promise<void> {
  const filters = { harness: props.harness, archived: props.archived };
  const key = JSON.stringify(filters);
  if (cache.has(key)) {
    projects.value = cache.get(key) || [];
    message.value = "";
    return;
  }
  if (loadingController) loadingController.abort();
  const controller = new AbortController();
  loadingController = controller;
  const currentRequest = ++requestNumber;
  message.value = t("loadingProjects");
  try {
    const data = await fetchProjects(filters, controller.signal);
    if (currentRequest !== requestNumber) return;
    projects.value = data.projects;
    cache.set(key, data.projects);
    message.value = "";
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") return;
    if (currentRequest !== requestNumber) return;
    message.value = error instanceof Error ? error.message : t("projectsLoadFailed");
  } finally {
    if (loadingController === controller) loadingController = null;
  }
}

function open(): void {
  isOpen.value = true;
  void load();
}

function onInputFocus(): void {
  open();
}

function onInputClick(): void {
  if (!isOpen.value) open();
}

function onInput(): void {
  const value = input.value?.value || "";
  query.value = value;
  emit("update:modelValue", value);
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    if (!isOpen.value) open();
    setActive(activeIndex.value + 1);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    if (isOpen.value) {
      setActive(activeIndex.value < 0 ? filtered.value.length - 1 : activeIndex.value - 1);
    }
  } else if (event.key === "Enter" && isOpen.value && activeIndex.value >= 0) {
    event.preventDefault();
    select(filtered.value[activeIndex.value]);
  } else if (event.key === "Escape") {
    event.preventDefault();
    close();
  } else if (event.key === "Tab") {
    close();
  }
}

function onToggle(): void {
  if (isOpen.value) {
    close();
  } else {
    input.value?.focus();
    open();
  }
}

function onDocumentClick(event: MouseEvent): void {
  const target = event.target as Node | null;
  if (!target) return;
  if (list.value?.contains(target)) return;
  if (input.value?.contains(target)) return;
  if (toggle.value?.contains(target)) return;
  close();
}

function refresh(): void {
  cache.clear();
  if (loadingController) loadingController.abort();
  requestNumber += 1;
  if (isOpen.value) void load();
}

onMounted(() => {
  document.addEventListener("click", onDocumentClick);
});

onBeforeUnmount(() => {
  document.removeEventListener("click", onDocumentClick);
  if (loadingController) loadingController.abort();
});

defineExpose({ close, refresh });
</script>

<template>
  <div class="filter-field project-field">
    <span id="cwd-label" class="visually-hidden">{{ t("projectDirectory") }}</span>
    <div class="project-input-wrap">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h7l2 2h9v11H3z"></path></svg>
      <input
        ref="input"
        class="project-input"
        name="cwd"
        type="text"
        :placeholder="t('projectPathHint')"
        autocomplete="off"
        spellcheck="false"
        role="combobox"
        aria-labelledby="cwd-label"
        aria-autocomplete="list"
        :aria-expanded="isOpen ? 'true' : 'false'"
        :aria-activedescendant="activeDescendant"
        aria-controls="cwd-options"
        :value="modelValue"
        @input="onInput"
        @focus="onInputFocus"
        @click="onInputClick"
        @keydown="onKeydown"
      >
      <button
        ref="toggle"
        class="project-toggle"
        type="button"
        :aria-label="t('projectSuggestions')"
        :aria-expanded="isOpen ? 'true' : 'false'"
        @click="onToggle"
      >
        <span aria-hidden="true">⌄</span>
      </button>
    </div>
    <ul
      v-show="isOpen"
      id="cwd-options"
      class="project-options"
      role="listbox"
      :aria-label="t('projectSuggestions')"
    >
      <li v-if="message" class="project-option-message">{{ message }}</li>
      <li v-if="!message && !filtered.length" class="project-option-message">
        {{ t("noProjects") }}
      </li>
      <li
        v-for="(path, index) in filtered"
        :key="path"
        class="project-option"
        :class="{ active: index === activeIndex }"
      >
        <button
          :id="`project-option-${index}`"
          type="button"
          role="option"
          :aria-selected="index === activeIndex ? 'true' : 'false'"
          :title="path"
          @mousedown.prevent
          @click="select(path)"
          @mousemove="setActive(index)"
        >
          {{ path }}
        </button>
      </li>
    </ul>
  </div>
</template>
