<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api'
import { productionStatusLabel } from '../ui/slotContentStatus'
import type { AccountPlanRecord, BatchSummary } from '../types'

const props = defineProps<{ accounts?: string[]; batches?: BatchSummary[]; inline?: boolean; filename?: string }>()
const opened = ref(false)
const start = ref('')
const end = ref('')
const busy = ref(false)
const error = ref('')

async function parallelMap<T, R>(items: T[], fn: (item: T) => Promise<R>): Promise<R[]> {
  const output: R[] = new Array(items.length)
  let next = 0
  await Promise.all(Array.from({ length: Math.min(8, items.length) }, async () => {
    while (next < items.length) {
      const index = next++
      output[index] = await fn(items[index]!)
    }
  }))
  return output
}

function cell(value: unknown) {
  let text = value == null ? '' : String(value)
  if (/^[\s]*[=+@\-\t\r]/.test(text)) text = `'${text}`
  return `"${text.replace(/"/g, '""')}"`
}

async function download() {
  error.value = ''
  if (props.accounts && (!start.value || !end.value || start.value > end.value)) {
    error.value = '请选择有效的开始日期和结束日期'
    return
  }
  busy.value = true
  try {
    let items: AccountPlanRecord[]
    if (props.accounts) {
      const rows = await parallelMap(props.accounts, account => api.accountItems(account, 5000))
      if (rows.some(row => row.length >= 5000)) throw new Error('部分账号策划记录达到查询上限，请联系管理员导出完整数据')
      items = rows.flatMap((row, index) => row.filter(item => item.account_id === props.accounts![index] && item.publish_date >= start.value && item.publish_date <= end.value))
    } else {
      const batches = props.batches || []
      if (batches.length >= 5000) throw new Error('批次数达到查询上限，请缩小筛选范围后导出')
      const rows = await parallelMap(batches, batch => api.batch(batch.id))
      items = rows.flatMap(batch => batch.items.map(item => ({ ...item, batch_id: batch.id, batch_code: batch.batch_code, batch_created_at: batch.created_at, plan_type: batch.plan_type, cycle_start: batch.cycle_start, cycle_end: batch.cycle_end })))
    }
    const adjustments = await parallelMap(items, item => api.adjustments(item.id))
    const headers = ['账号ID', '账号昵称', '投放日期', '批次号', '策划方式', '选题ID', '选题标题', '选题大纲', '选题二级分类', '内容状态', '最新操作', '操作人', '操作时间', '操作说明']
    const rows = items.map((item, index) => {
      const latest = adjustments[index]?.[0]
      const useAdjustment = latest && (!item.batch_created_at || latest.created_at >= item.batch_created_at)
      return [item.account_id, item.account_name, item.publish_date, item.batch_code, item.plan_type === 'manual' ? '人工策划' : '自动策划', item.topic_id, item.topic_title, item.outline, item.content_type, productionStatusLabel(item), useAdjustment ? latest.adjustment_source : item.batch_created_at ? '策划结果生成' : '', useAdjustment ? latest.created_by : item.batch_created_at ? (item.plan_type === 'manual' ? '人工策划' : 'AI 自动策划') : '', useAdjustment ? latest.created_at : item.batch_created_at, useAdjustment ? `${latest.old_topic_title || latest.old_topic_id} → ${latest.new_topic_title || latest.new_topic_id}${latest.reason ? ` · ${latest.reason}` : ''}` : '']
    })
    const data = '\ufeff' + [headers, ...rows].map(row => row.map(cell).join(',')).join('\r\n')
    const url = URL.createObjectURL(new Blob([data], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = props.filename || `${props.accounts ? '账号' : '时间'}策划明细.csv`
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
        <h3 id="export-title">导出策划明细</h3>
        <div v-if="accounts" class="export-dates"><label>开始日期 <input v-model="start" type="date" /></label><label>结束日期 <input v-model="end" type="date" /></label></div>
        <p v-if="error" class="export-error" role="alert">{{ error }}</p>
        <div class="export-actions"><button class="btn" type="button" :disabled="busy" @click="opened = false">取消</button><button class="btn primary" type="button" :disabled="busy" @click="download">{{ busy ? '导出中…' : '确认导出' }}</button></div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.export-mask{position:fixed;inset:0;z-index:300;background:var(--mask);display:flex;align-items:center;justify-content:center}.export-dialog{box-sizing:border-box;width:min(440px,calc(100vw - 24px));padding:24px;background:var(--surface);border-radius:4px;box-shadow:var(--shadow-4)}h3{margin:0 0 20px}.export-dates{display:flex;gap:16px}.export-dates label{display:flex;flex:1;min-width:0;flex-direction:column;gap:8px;color:var(--neutral-600);font-size:13px}.export-dates input{width:100%;height:32px;box-sizing:border-box;padding:0 8px;border:1px solid var(--neutral-200);border-radius:4px;color:var(--neutral-900);font:inherit}.export-dates input:focus{outline:none;border-color:var(--primary-600);box-shadow:var(--focus-ring)}.export-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:24px}.export-error{color:var(--danger);font-size:13px}@media(max-width:400px){.export-dates{flex-direction:column;gap:12px}}
</style>
