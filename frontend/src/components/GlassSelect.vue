<script setup lang="ts">
import { ref, computed, nextTick, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'

interface Option { label: string; value: string | number }
const props = defineProps<{
  modelValue: string | number | null
  options: Option[]
  placeholder?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [string | number] }>()
const { t } = useI18n()

const open = ref(false)
const trigger = ref<HTMLElement | null>(null)
const menuStyle = ref<Record<string, string>>({})

const current = computed(
  () => props.options.find((o) => o.value === props.modelValue)?.label
    ?? props.placeholder ?? t('common.select')
)

function place() {
  const el = trigger.value
  if (!el) return
  const r = el.getBoundingClientRect()
  menuStyle.value = {
    position: 'fixed',
    top: `${r.bottom + 6}px`,
    left: `${r.left}px`,
    width: `${r.width}px`,
  }
}

async function toggle() {
  open.value = !open.value
  if (open.value) {
    await nextTick()
    place()
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
  } else {
    detach()
  }
}

function detach() {
  window.removeEventListener('scroll', place, true)
  window.removeEventListener('resize', place)
}

function pick(o: Option) {
  emit('update:modelValue', o.value)
  open.value = false
  detach()
}

onBeforeUnmount(detach)
</script>

<template>
  <div class="glass-select" :class="{ open }">
    <button ref="trigger" type="button" class="gs-trigger" @click="toggle">
      <span>{{ current }}</span>
      <span class="gs-arrow">▾</span>
    </button>
    <Teleport to="body">
      <transition name="gs-fade">
        <ul v-if="open" class="gs-menu" :style="menuStyle">
          <li
            v-for="o in options"
            :key="o.value"
            class="gs-item"
            :class="{ active: o.value === modelValue }"
            @click="pick(o)"
          >
            {{ o.label }}
          </li>
        </ul>
      </transition>
      <div v-if="open" class="gs-backdrop" @click="open = false; detach()" />
    </Teleport>
  </div>
</template>

<style scoped>
.glass-select { position: relative; display: inline-block; min-width: 140px; }
.gs-trigger {
  width: 100%; display: flex; justify-content: space-between; align-items: center;
  gap: 8px; padding: 8px 12px; border-radius: 10px;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  color: var(--fg); cursor: pointer; backdrop-filter: blur(12px);
}
.gs-arrow { transition: transform .2s; opacity: .7; }
.glass-select.open .gs-arrow { transform: rotate(180deg); }
.gs-fade-enter-active, .gs-fade-leave-active { transition: opacity .15s, transform .15s; }
.gs-fade-enter-from, .gs-fade-leave-to { opacity: 0; transform: translateY(-4px); }
</style>

<style>
/* 菜单 teleport 到 body,样式需为全局(非 scoped)。z-index 高于所有页面元素。 */
.gs-menu {
  z-index: 9999;
  margin: 0; padding: 6px; list-style: none; max-height: 300px; overflow-y: auto;
  background: var(--glass-bg-strong); border: 1px solid var(--glass-border);
  border-radius: 12px; backdrop-filter: blur(20px);
  box-shadow: 0 8px 32px rgba(0,0,0,.25);
}
.gs-menu .gs-item { padding: 8px 10px; border-radius: 8px; color: var(--fg); cursor: pointer; }
.gs-menu .gs-item:hover { background: rgba(255,255,255,.08); }
.gs-menu .gs-item.active { background: var(--accent); color: #fff; }
.gs-backdrop { position: fixed; inset: 0; z-index: 9998; }
</style>
