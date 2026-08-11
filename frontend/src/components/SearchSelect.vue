<script setup lang="ts">
import { ref, computed, nextTick, onBeforeUnmount } from "vue";
import { useI18n } from "vue-i18n";

interface Option { label: string; value: string | number }
const props = defineProps<{
  modelValue: string | number | null;
  options: Option[];
  placeholder?: string;
}>();
const emit = defineEmits<{ "update:modelValue": [string | number] }>();
const { t } = useI18n();

const open = ref(false);
const keyword = ref("");
const trigger = ref<HTMLElement | null>(null);
const panelStyle = ref<Record<string, string>>({});

const current = computed(
  () => props.options.find((o) => o.value === props.modelValue)?.label
    ?? props.placeholder ?? t("common.select")
);

const filtered = computed(() => {
  const kw = keyword.value.toLowerCase();
  return kw
    ? props.options.filter((o) => String(o.label).toLowerCase().includes(kw))
    : props.options;
});

function place() {
  const el = trigger.value;
  if (!el) return;
  const r = el.getBoundingClientRect();
  panelStyle.value = {
    position: "fixed",
    top: `${r.bottom + 6}px`,
    left: `${r.left}px`,
    width: `${Math.max(r.width, 200)}px`,
  };
}
async function toggle() {
  open.value = !open.value;
  if (open.value) {
    keyword.value = "";
    await nextTick();
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
  } else detach();
}
function detach() {
  window.removeEventListener("scroll", place, true);
  window.removeEventListener("resize", place);
}
function pick(o: Option) {
  emit("update:modelValue", o.value);
  open.value = false;
  keyword.value = "";
  detach();
}
onBeforeUnmount(detach);
</script>

<template>
  <div class="search-select" :class="{ open }">
    <button ref="trigger" type="button" class="ss-trigger" @click="toggle">
      <span>{{ current }}</span>
      <span class="ss-arrow">▾</span>
    </button>
    <Teleport to="body">
      <transition name="ss-fade">
        <div v-if="open" class="ss-panel" :style="panelStyle">
          <input v-model="keyword" class="ss-search" :placeholder="t('common.search')" />
          <ul class="ss-list">
            <li v-if="!filtered.length" class="ss-empty">{{ t("common.noMatch") }}</li>
            <li
              v-for="o in filtered"
              :key="o.value"
              class="ss-item"
              :class="{ active: o.value === modelValue }"
              @click="pick(o)"
            >
              {{ o.label }}
            </li>
          </ul>
        </div>
      </transition>
      <div v-if="open" class="ss-backdrop" @click="open = false; detach()" />
    </Teleport>
  </div>
</template>

<style scoped>
.search-select { position: relative; display: inline-block; min-width: 160px; }
.ss-trigger {
  width: 100%; display: flex; justify-content: space-between; align-items: center;
  gap: 8px; padding: 8px 12px; border-radius: 10px;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  color: var(--fg); cursor: pointer; backdrop-filter: blur(12px);
}
.ss-arrow { opacity: .7; transition: transform .2s; }
.search-select.open .ss-arrow { transform: rotate(180deg); }
.ss-fade-enter-active, .ss-fade-leave-active { transition: opacity .15s, transform .15s; }
.ss-fade-enter-from, .ss-fade-leave-to { opacity: 0; transform: translateY(-4px); }
</style>

<style>
/* teleport 到 body,需全局样式;与 SymbolSelect 等价,使 SearchSelect 自包含 */
.ss-panel {
  z-index: 9999;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  padding: 8px;
  backdrop-filter: blur(20px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
}
.ss-search {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  margin-bottom: 6px;
  border-radius: 8px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  color: var(--fg);
  outline: none;
}
.ss-list { list-style: none; margin: 0; padding: 0; max-height: 240px; overflow-y: auto; }
.ss-item { padding: 8px 10px; border-radius: 8px; color: var(--fg); cursor: pointer; }
.ss-item:hover { background: rgba(255, 255, 255, 0.08); }
.ss-item.active { background: var(--accent); color: #fff; }
.ss-empty { padding: 10px; text-align: center; opacity: 0.6; color: var(--fg); }
.ss-backdrop { position: fixed; inset: 0; z-index: 9998; }
</style>
