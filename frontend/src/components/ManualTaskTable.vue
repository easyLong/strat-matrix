<script setup lang="ts">
import LoadingSkeleton from './LoadingSkeleton.vue'
import type { ManualTaskSummary } from '../types'
import { formatDateTime } from '../planningTime'

defineProps<{
  tasks: ManualTaskSummary[]
  loading: boolean
  initialized: boolean
}>()

const emit = defineEmits<{
  planDetails: [task: ManualTaskSummary]
  generateContent: [task: ManualTaskSummary]
  contentFlow: [task: ManualTaskSummary]
}>()

function planningLabel(task: ManualTaskSummary) {
  return task.planning_status || task.status || '—'
}

function planningTone(task: ManualTaskSummary) {
  const label = planningLabel(task)
  if (/部分失败/.test(label)) return 'orange'
  if (/失败|异常|错误/.test(label)) return 'red'
  if (/进行中|执行中|处理中|策划中|生成中/.test(label)) return 'blue'
  if (/完成|成功/.test(label)) return 'green'
  return 'gray'
}

function contentLabel(task: ManualTaskSummary) {
  const raw = (task.content_status || '').trim()
  const hasCompleted = task.content_completed_count > 0 || task.content_completed_account_count > 0
  const hasFailures = task.content_failed_count > 0
  if (hasCompleted && hasFailures) return '部分失败'
  if (hasFailures && !hasCompleted) return '生成失败'
  if (/待生产|待生成|未生成/.test(raw)) return '待生成'
  if (/生产中|生成中|上传中/.test(raw)) return '生成中'
  if (/已完成|已生成|已发布/.test(raw)) return '已完成'
  if (/失败|异常|错误/.test(raw)) return '生成失败'
  if (!raw && !task.batch_id) return '—'
  return raw || '待生成'
}

function contentTone(task: ManualTaskSummary) {
  const label = contentLabel(task)
  if (label === '待生成' || label === '—') return 'gray'
  if (label === '生成中') return 'blue'
  if (label === '已完成') return 'green'
  if (label === '部分失败') return 'orange'
  if (label === '生成失败') return 'red'
  return 'gray'
}

function contentProgress(task: ManualTaskSummary) {
  const label = contentLabel(task)
  if (label === '—') return ''
  const totalAccounts = Math.max(task.planned_account_count || 0, 0)
  const completedAccounts = Math.max(task.content_completed_account_count || 0, 0)
  if (label === '待生成') return totalAccounts ? `0 / ${totalAccounts}` : '尚未开始'
  if (label === '部分失败') {
    const failed = Math.max(task.content_failed_count || 0, 0)
    const base = totalAccounts ? `${completedAccounts} / ${totalAccounts}` : `${task.content_completed_count || 0} 已完成`
    return failed ? `${base} · ${failed} 失败` : base
  }
  if (totalAccounts) return `${Math.min(completedAccounts, totalAccounts)} / ${totalAccounts}`
  const totalContent = Math.max(task.content_total_count || 0, 0)
  if (totalContent) return `${Math.min(task.content_completed_count || 0, totalContent)} / ${totalContent}`
  return ''
}

function canGenerate(task: ManualTaskSummary) {
  return Boolean(task.batch_id) && /完成|成功/.test(planningLabel(task)) && contentLabel(task) === '待生成'
}
</script>

<template>
  <LoadingSkeleton v-if="!initialized || (loading && !tasks.length)" :rows="7" />
  <div v-else class="manual-task-table-wrap">
    <table class="manual-task-table">
      <thead>
        <tr>
          <th>批次名称</th>
          <th>投放日期</th>
          <th>账号数</th>
          <th>选题数</th>
          <th>策划状态</th>
          <th>内容状态</th>
          <th>批次号</th>
          <th>发起时间</th>
          <th>更新时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="task in tasks" :key="task.id" :class="{ 'has-failures': task.failure_count > 0 }">
          <td><b>{{ task.task_name || '—' }}</b></td>
          <td>{{ task.publish_date }}</td>
          <td class="numeric">{{ task.planned_account_count }}</td>
          <td class="numeric">{{ task.topic_count }}</td>
          <td><span :class="['tag', planningTone(task)]">{{ planningLabel(task) }}</span></td>
          <td>
            <div class="manual-content-status">
              <span :class="['tag', contentTone(task)]">{{ contentLabel(task) }}</span>
              <small v-if="contentProgress(task)">{{ contentProgress(task) }}</small>
            </div>
          </td>
          <td class="identifier">{{ task.batch_code || '—' }}</td>
          <td class="date-cell">{{ formatDateTime(task.created_at) }}</td>
          <td class="date-cell">{{ formatDateTime(task.updated_at) }}</td>
          <td class="action-cell">
            <div class="manual-task-actions">
              <button v-if="task.batch_id" class="text-btn" type="button" @click="emit('planDetails', task)">策划详情</button>
              <button v-if="canGenerate(task)" class="text-btn manual-primary-action" type="button" @click="emit('generateContent', task)">生成内容</button>
              <button v-if="task.batch_id" class="text-btn manual-content-flow-link" type="button" @click="emit('contentFlow', task)">内容流水</button>
              <span v-if="!task.batch_id" class="manual-action-empty">—</span>
            </div>
          </td>
        </tr>
        <tr v-if="tasks.length === 0"><td colspan="10"><div class="empty-state">暂无人工策划任务</div></td></tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.manual-task-table-wrap{max-height:calc(100vh - 260px);overflow:auto}
.manual-task-table{width:100%;min-width:1080px;border-collapse:collapse}
.manual-task-table th{position:sticky;top:0;z-index:2;padding:12px 14px;background:var(--neutral-50);color:var(--neutral-500);font-size:12px;font-weight:500;line-height:20px;text-align:left;white-space:nowrap}
.manual-task-table td{height:56px;padding:10px 14px;border-top:1px solid var(--neutral-100);color:var(--neutral-600);font-size:13px;line-height:20px;vertical-align:middle}
.manual-task-table tbody tr:hover{background:var(--hover-bg)}
.manual-task-table tbody tr.has-failures{background:var(--processing-row)}
.manual-task-table tbody tr.has-failures:hover{background:var(--processing-bg)}
.manual-task-table td:first-child{min-width:150px;max-width:220px;color:var(--neutral-800);font-weight:500;overflow-wrap:anywhere}
.manual-task-table .numeric{text-align:center;font-variant-numeric:tabular-nums;white-space:nowrap}
.manual-task-table .identifier,.manual-task-table .date-cell{color:var(--neutral-500);font-variant-numeric:tabular-nums;white-space:nowrap}
.manual-task-table .tag{display:inline-flex;align-items:center;min-height:24px;padding:2px 8px;border-radius:6px;font-size:12px;font-weight:500;line-height:18px;white-space:nowrap}
.manual-content-status{display:flex;align-items:center;gap:8px;min-width:118px;white-space:nowrap}
.manual-content-status small{color:var(--neutral-400);font-size:11px;font-variant-numeric:tabular-nums}
.action-cell{position:sticky;right:0;z-index:1;min-width:230px;background:var(--surface);box-shadow:-1px 0 0 var(--neutral-100)}
tr:hover .action-cell{background:var(--hover-bg)}
tr.has-failures .action-cell{background:var(--processing-row)}
tr.has-failures:hover .action-cell{background:var(--processing-bg)}
.manual-task-actions{display:flex;align-items:center;gap:14px;white-space:nowrap}
.manual-task-actions .text-btn{padding:0;border:0;background:transparent;font-size:12px;line-height:20px}
.manual-primary-action{font-weight:600}
.manual-content-flow-link{color:var(--neutral-600)}
.manual-content-flow-link:hover{color:var(--primary-600)}
.manual-action-empty{color:var(--neutral-300)}
@media(max-width:900px){.manual-task-table{min-width:980px}.action-cell{min-width:216px}.manual-task-actions{gap:10px}}
</style>
