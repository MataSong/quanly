<script setup lang="ts">
import { ref, computed, onMounted, nextTick, onBeforeUnmount } from "vue";
import { useI18n } from "vue-i18n";
import client from "@/api/client";

defineProps<{ modelValue: string }>();
const emit = defineEmits<{ "update:modelValue": [string] }>();
const { t } = useI18n();

const open = ref(false);
const keyword = ref("");
const loading = ref(false);
const activeType = ref("SPOT");
const byType = ref<Record<string, { instId: string }[]>>({});

const trigger = ref<HTMLElement | null>(null);
const panelStyle = ref<Record<string, string>>({});

const TYPES = [
  { key: "SPOT", label: "market.spot" },
  { key: "SWAP", label: "market.swap" },
  { key: "FUTURES", label: "market.futures" },
  { key: "OPTION", label: "market.option" },
];

const availableTypes = computed(() =>
  TYPES.filter((tp) => (byType.value[tp.key]?.length ?? 0) > 0)
);

const filtered = computed(() => {
  const list = (byType.value[activeType.value] ?? []).map((i) => i.instId);
  const kw = keyword.value.toLowerCase();
  return kw ? list.filter((s) => s.toLowerCase().includes(kw)) : list;
});

async function load() {
  loading.value = true;
  try {
    const { data } = await client.get("/market/symbols");
    if (data.by_type) {
      byType.value = data.by_type;
      if (!byType.value[activeType.value]?.length && availableTypes.value.length) {
        activeType.value = availableTypes.value[0].key;
      }
    } else {
      // 兼容旧格式:扁平 symbols
      const flat = (data.symbols ?? data ?? []).map((x: any) =>
        typeof x === "string" ? { instId: x } : { instId: x.symbol }
      );
      byType.value = { SPOT: flat };
    }
  } finally {
    loading.value = false;
  }
}

function place() {
  const el = trigger.value;
  if (!el) return;
  const r = el.getBoundingClientRect();
  panelStyle.value = {
    position: "fixed",
    top: `${r.bottom + 6}px`,
    left: `${r.left}px`,
    width: `${Math.max(r.width, 240)}px`,
  };
}

async function toggle() {
  open.value = !open.value;
  if (open.value) {
    await nextTick();
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
  } else {
    detach();
  }
}

function detach() {
  window.removeEventListener("scroll", place, true);
  window.removeEventListener("resize", place);
}

function pick(s: string) {
  emit("update:modelValue", s);
  open.value = false;
  keyword.value = "";
  detach();
}

onMounted(load);
onBeforeUnmount(detach);
</script>

<template>
  <div class="symbol-select" :class="{ open }">
    <button ref="trigger" type="button" class="ss-trigger" @click="toggle">
      <span>{{ modelValue || t("market.selectSymbol") }}</span>
      <span class="ss-arrow">▾</span>
    </button>
    <Teleport to="body">
      <transition name="ss-fade">
        <div v-if="open" class="ss-panel" :style="panelStyle">
          <div class="ss-tabs">
            <button
              v-for="tp in availableTypes"
              :key="tp.key"
              type="button"
              class="ss-tab"
              :class="{ active: tp.key === activeType }"
              @click="activeType = tp.key"
            >
              {{ t(tp.label) }}
            </button>
          </div>
          <input
            v-model="keyword"
            class="ss-search"
            :placeholder="t('market.searchSymbol')"
          />
          <ul class="ss-list">
            <li v-if="loading" class="ss-empty">{{ t("common.loading") }}</li>
            <li v-else-if="!filtered.length" class="ss-empty">{{ t("common.noMatch") }}</li>
            <li
              v-for="s in filtered"
              :key="s"
              class="ss-item"
              :class="{ active: s === modelValue }"
              @click="pick(s)"
            >
              {{ s }}
            </li>
          </ul>
        </div>
      </transition>
      <div v-if="open" class="ss-backdrop" @click="open = false; detach()" />
    </Teleport>
  </div>
</template>

<style scoped>
.symbol-select {
  position: relative;
  display: inline-block;
  min-width: 180px;
}
.ss-trigger {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-radius: 10px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  color: var(--fg);
  cursor: pointer;
  backdrop-filter: blur(12px);
}
.ss-arrow {
  opacity: 0.7;
  transition: transform 0.2s;
}
.symbol-select.open .ss-arrow {
  transform: rotate(180deg);
}
.ss-fade-enter-active,
.ss-fade-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}
.ss-fade-enter-from,
.ss-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>

<style>
/* teleport 到 body,需全局样式;z-index 高于所有页面元素避免遮挡 */
.ss-panel {
  z-index: 9999;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  padding: 8px;
  backdrop-filter: blur(20px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
}
.ss-tabs { display: flex; gap: 4px; margin-bottom: 6px; }
.ss-tab {
  flex: 1; padding: 5px 6px; border-radius: 8px; font-size: 12px;
  background: transparent; border: 1px solid var(--glass-border);
  color: var(--fg-dim); cursor: pointer;
}
.ss-tab.active { background: var(--accent); border-color: var(--accent); color: #fff; }
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
