<script setup lang="ts">
import { computed } from 'vue'
const props = withDefaults(defineProps<{ page: number; pageSize: number; total: number; unit?: string; pageSizeOptions?: number[] }>(), { unit: '条', pageSizeOptions: () => [10, 20, 50] })
const emit = defineEmits<{ 'update:page': [value: number]; 'update:pageSize': [value: number] }>()
const count = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const pages = computed(() => {
  const numbers = new Set([1, count.value])
  for (let p = Math.max(1, props.page - 1); p <= Math.min(count.value, props.page + 1); p++) numbers.add(p)
  const sorted = [...numbers].sort((a, b) => a - b)
  return sorted.flatMap((page, index) => index && page - sorted[index - 1] > 1 ? [`gap-${page}`, page] : [page])
})
function changeSize(event: Event) {
  emit('update:pageSize', Number((event.target as HTMLSelectElement).value))
  emit('update:page', 1)
}
</script>
<template>
  <nav class="account-pagination" aria-label="分页">
    <span class="pagination-total">共 {{ total }} {{ unit }}</span>
    <label>每页 <select :value="pageSize" aria-label="每页数量" @change="changeSize"><option v-for="size in pageSizeOptions" :key="size" :value="size">{{ size }}</option></select> {{ unit }}</label>
    <button class="btn" type="button" :disabled="page <= 1" @click="emit('update:page', page - 1)">上一页</button>
    <template v-for="value in pages" :key="value"><button v-if="typeof value === 'number'" :class="value === page ? 'current-page' : 'btn pagination-number'" :aria-current="value === page ? 'page' : undefined" :aria-label="`第 ${value} 页`" type="button" @click="emit('update:page', value)">{{ value }}</button><span v-else aria-hidden="true">…</span></template>
    <button class="btn" type="button" :disabled="page >= count" @click="emit('update:page', page + 1)">下一页</button>
  </nav>
</template>
