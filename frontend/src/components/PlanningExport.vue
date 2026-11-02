<script setup lang="ts">
import { ref } from 'vue'
import type { PlanPageQuery } from '../api/queries'
import type { BatchSummary } from '../types'
import PageBreadcrumbs from './PageBreadcrumbs.vue'
import { usePageBreadcrumbs } from '../composables/usePageBreadcrumbs'

const props = defineProps<{ accounts?: string[]; batches?: BatchSummary[]; inline?: boolean; filename?: string; scope?: PlanPageQuery; accountDates?: boolean }>()
const opened = ref(false)
const start = ref('')
const end = ref('')
const busy = ref(false)
const error = ref('')
usePageBreadcrumbs(() => opened.value ? [{ label: '导出报表' }] : [], { append: true, close: () => { if (!busy.value) opened.value = false } })

async function download() {
  error.value = ''
  if ((props.accounts || props.accountDates) && (!start.value || !end.value || start.value > end.value)) {
    error.value = '请选择有效的开始日期和结束日期'
    return
  }
  busy.value = true
  try {
    const scope = props.scope || { mode: 'all' as const, page: 1, page_size: 200, filters: {}, account_ids: props.accounts, batch_ids: props.accounts ? undefined : (props.batches || []).map(b=>b.id) }
    const response = await fetch('/api/query/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...scope, filters: { ...scope.filters, ...((props.accounts || props.accountDates) ? {start:start.value,end:end.value}: {}) } }) })
    if (!response.ok) { const body=await response.json(); throw new Error(body.detail || '导出失败，请重试') }
    const data = await response.blob()
    const url = URL.createObjectURL(data)
    const link = document.createElement('a')
    link.href = url
    link.download = props.filename || `${props.accounts || props.accountDates ? '账号' : '时间'}策划明细.csv`
    link.click()
    URL.revokeObjectURL(url)
    opened.value = false
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '导出失败，请重试'
  } finally { busy.value = false }
}
</script>

<template>
  <button type="button" :class="inline ? 'text-btn' : 'btn'" @click="opened = true">导出报表</button>
  <Teleport to="body">
    <div v-if="opened" class="export-mask" @click.self="!busy && (opened = false)">
      <section class="export-dialog" role="dialog" aria-modal="true" aria-labelledby="export-title">
        <PageBreadcrumbs compact />
        <h3 id="export-title">导出策划明细</h3>
        <div v-if="accounts || accountDates" class="export-dates"><label>开始日期 <input v-model="start" type="date" /></label><label>结束日期 <input v-model="end" type="date" /></label></div>
        <p v-if="error" class="export-error" role="alert">{{ error }}</p>
        <div class="export-actions"><button class="btn" type="button" :disabled="busy" @click="opened = false">取消</button><button class="btn primary" type="button" :disabled="busy" @click="download">{{ busy ? '导出中…' : '确认导出' }}</button></div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.export-mask{position:fixed;inset:0;z-index:300;background:var(--mask);display:flex;align-items:center;justify-content:center}.export-dialog{box-sizing:border-box;width:min(440px,calc(100vw - 24px));padding:24px;background:var(--surface);border-radius:4px;box-shadow:var(--shadow-4)}h3{margin:0 0 20px}.export-dates{display:flex;gap:16px}.export-dates label{display:flex;flex:1;min-width:0;flex-direction:column;gap:8px;color:var(--neutral-600);font-size:13px}.export-dates input{width:100%;height:32px;box-sizing:border-box;padding:0 8px;border:1px solid var(--neutral-200);border-radius:4px;color:var(--neutral-900);font:inherit}.export-dates input:focus{outline:none;border-color:var(--primary-600);box-shadow:var(--focus-ring)}.export-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:24px}.export-error{color:var(--danger);font-size:13px}@media(max-width:400px){.export-dates{flex-direction:column;gap:12px}}
</style>
