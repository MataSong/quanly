<template>
  <div v-if="password.length > 0" class="pw-strength">
    <!-- Strength bar -->
    <div class="bar-row">
      <span class="bar-label">{{ t("password.strength") }}</span>
      <div class="bars">
        <div class="bar" :class="barClass(1)" />
        <div class="bar" :class="barClass(2)" />
        <div class="bar" :class="barClass(3)" />
        <div class="bar" :class="barClass(4)" />
      </div>
      <span class="level-label" :class="levelClass">{{ levelText }}</span>
    </div>
    <!-- Rule checklist -->
    <ul class="rules">
      <li :class="{ ok: rules.minLen, fail: !rules.minLen }">
        <span class="icon">{{ rules.minLen ? "✓" : "✗" }}</span>
        {{ t("password.ruleMinLen") }}
      </li>
      <li :class="{ ok: rules.upper, fail: !rules.upper }">
        <span class="icon">{{ rules.upper ? "✓" : "✗" }}</span>
        {{ t("password.ruleUpper") }}
      </li>
      <li :class="{ ok: rules.lower, fail: !rules.lower }">
        <span class="icon">{{ rules.lower ? "✓" : "✗" }}</span>
        {{ t("password.ruleLower") }}
      </li>
      <li :class="{ ok: rules.digit, fail: !rules.digit }">
        <span class="icon">{{ rules.digit ? "✓" : "✗" }}</span>
        {{ t("password.ruleDigit") }}
      </li>
      <li :class="{ ok: rules.special, fail: !rules.special }">
        <span class="icon">{{ rules.special ? "✓" : "✗" }}</span>
        {{ t("password.ruleSpecial") }}
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { scorePassword, checkRules } from "@/utils/password";

const props = defineProps<{ password: string }>();
const { t } = useI18n();

const scored = computed(() => scorePassword(props.password));
const rules = computed(() => checkRules(props.password));

const levelText = computed(() => {
  if (scored.value.level === "weak") return t("password.weak");
  if (scored.value.level === "medium") return t("password.medium");
  return t("password.strong");
});

const levelClass = computed(() => scored.value.level);

function barClass(barIndex: number): string {
  const score = scored.value.score;
  if (barIndex > score) return "empty";
  if (score <= 1) return "weak";
  if (score === 2) return "medium";
  return "strong";
}
</script>

<style scoped>
.pw-strength {
  margin-top: 8px;
  font-size: 12px;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.bar-label {
  color: var(--gray-500, #6b7280);
  white-space: nowrap;
}

.bars {
  display: flex;
  gap: 3px;
  flex: 1;
}

.bar {
  height: 4px;
  flex: 1;
  border-radius: 2px;
  background: var(--gray-200, #e5e7eb);
  transition: background 0.2s;
}
.bar.weak   { background: #ef4444; }
.bar.medium { background: #f59e0b; }
.bar.strong { background: #10b981; }

.level-label {
  font-weight: 600;
  white-space: nowrap;
}
.level-label.weak   { color: #ef4444; }
.level-label.medium { color: #f59e0b; }
.level-label.strong { color: #10b981; }

.rules {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.rules li {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--gray-400, #9ca3af);
}
.rules li.ok   { color: #10b981; }
.rules li.fail { color: var(--gray-400, #9ca3af); }

.icon { font-size: 11px; width: 12px; text-align: center; }
</style>
