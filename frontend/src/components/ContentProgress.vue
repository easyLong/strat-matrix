<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ completed: number; total: number; display?: 'progress' | 'status' }>(), { display: 'progress' })
const description = computed(() => `完成内容生产 ${props.completed} 个账号 / 共 ${props.total} 个账号`)
const statusLabel = computed(() => {
  if (props.total > 0 && props.completed >= props.total) return '已完成'
  if (props.completed > 0) return '生成中'
  return '待生成'
})
const statusTone = computed(() => statusLabel.value === '已完成' ? 'status-completed' : statusLabel.value === '生成中' ? 'status-processing' : 'status-waiting')
</script>

<template>
  <span v-if="display === 'status'" :class="['content-status', statusTone]" :title="description" :aria-label="`${statusLabel}（${completed}/${total}）`">
    <b>{{ statusLabel }}</b><span>（{{ completed }}/{{ total }}）</span>
  </span>
  <span v-else class="content-progress" :title="description" :aria-label="description">
    <span :class="{ completed: completed > 0 }">{{ completed }}</span>
    <span class="separator" aria-hidden="true">/</span>
    <span class="total">{{ total }}</span>
  </span>
</template>

<style scoped>
.content-progress{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;color:var(--neutral-400);font-variant-numeric:tabular-nums}
.completed{color:var(--success);font-weight:600}
.separator{color:var(--neutral-300);font-weight:400}
.total{color:var(--neutral-700);font-weight:500}
.content-status{display:inline-flex;align-items:center;gap:5px;white-space:nowrap;font-variant-numeric:tabular-nums}.content-status b{font-weight:600}.content-status>span{color:var(--neutral-500);font-weight:500}.status-completed b{color:var(--success)}.status-processing b{color:var(--primary-600)}.status-waiting b{color:var(--neutral-500)}
</style>
