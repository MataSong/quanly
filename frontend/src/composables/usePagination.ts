import { computed, ref, watch, type Ref } from "vue";

// 市面流行的每页行数选项
export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

export function usePagination<T>(source: Ref<T[]>, defaultSize = 10) {
  const page = ref(1);
  const pageSize = ref(defaultSize);

  const total = computed(() => source.value.length);
  const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));

  const paged = computed(() => {
    const start = (page.value - 1) * pageSize.value;
    return source.value.slice(start, start + pageSize.value);
  });

  // 数据变化或换每页行数后,页码越界则回落
  watch([total, pageSize], () => {
    if (page.value > totalPages.value) page.value = totalPages.value;
  });

  return { page, pageSize, total, totalPages, paged };
}
