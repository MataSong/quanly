<template>
  <!-- PC: 原生 el-table;手机: 卡片列表 -->
  <div class="responsive-table">
    <!-- 桌面端 -->
    <el-table
      v-if="!isMobile"
      :data="data"
      size="small"
      border
      :row-key="rowKey"
      style="width: 100%"
    >
      <el-table-column
        v-for="col in columns"
        :key="col.prop"
        :prop="col.prop"
        :label="col.label"
        :width="col.width"
        :min-width="col.minWidth"
        :align="col.align || 'left'"
        :fixed="col.fixed"
      >
        <template #default="scope">
          <!-- 具名 slot 优先(如操作列/着色单元格): #cell-<prop> -->
          <slot :name="`cell-${col.prop}`" :row="scope.row" :value="scope.row[col.prop]">
            <span :class="cellClass(col, scope.row)">
              {{ formatCell(col, scope.row) }}
            </span>
          </slot>
        </template>
      </el-table-column>
    </el-table>

    <!-- 移动端:卡片列表 -->
    <div v-else class="card-list">
      <el-empty v-if="!data || data.length === 0" :description="emptyText" :image-size="72" />
      <div v-for="(row, idx) in data" :key="rowKey ? row[rowKey] : idx" class="data-card">
        <div v-for="col in columns" :key="col.prop" class="card-row">
          <span class="card-label">{{ col.label }}</span>
          <span class="card-value">
            <slot :name="`cell-${col.prop}`" :row="row" :value="row[col.prop]">
              <span :class="cellClass(col, row)">{{ formatCell(col, row) }}</span>
            </slot>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useBreakpoint } from "@/composables/useBreakpoint";

export interface RTColumn {
  prop: string;
  label: string;
  width?: number | string;
  minWidth?: number | string;
  align?: "left" | "center" | "right";
  fixed?: boolean | "left" | "right";
  /** 值格式化:返回展示文本 */
  formatter?: (row: Record<string, any>, value: any) => string;
  /** 返回单元格 class(如 profit/loss 着色) */
  cellClass?: (row: Record<string, any>, value: any) => string;
}

const props = defineProps<{
  columns: RTColumn[];
  data: Record<string, any>[];
  rowKey?: string;
  emptyText?: string;
}>();

const { isMobile } = useBreakpoint();

function formatCell(col: RTColumn, row: Record<string, any>): string {
  const v = row[col.prop];
  if (col.formatter) return col.formatter(row, v);
  return v == null ? "" : String(v);
}

function cellClass(col: RTColumn, row: Record<string, any>): string {
  return col.cellClass ? col.cellClass(row, row[col.prop]) : "";
}
</script>

<style scoped lang="scss">
@use "@/styles/mixins" as *;

.responsive-table {
  width: 100%;
}

/* 卡片列表(移动端) */
.card-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.data-card {
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  background: #fff;
  padding: var(--space-3) var(--space-4);
  box-shadow: var(--shadow-xs);
}
.card-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 4px 0;
  border-bottom: 1px solid var(--gray-100);
}
.card-row:last-child {
  border-bottom: none;
}
.card-label {
  flex: none;
  color: var(--gray-500);
  font-size: var(--font-size-sm);
}
.card-value {
  flex: 1;
  text-align: right;
  word-break: break-all;
  font-size: var(--font-size-md);
  color: var(--gray-800);
}

/* 盈亏着色(与 Trading.vue 一致) */
:deep(.profit) {
  color: #26a17b;
  font-weight: 500;
}
:deep(.loss) {
  color: #e84646;
  font-weight: 500;
}
</style>
