import type { ManualTaskSummary } from '../types'

export function manualPlanningLabel(task: ManualTaskSummary) {
  return task.planning_status || task.status || '—'
}

export function manualContentLabel(task: ManualTaskSummary) {
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

export interface ManualTaskFilters {
  batch: string
  dateStart: string
  dateEnd: string
  creator: string
  planningStatus: string
  contentStatus: string
}

export function matchesManualTask(task: ManualTaskSummary, filters: ManualTaskFilters) {
  const batch = filters.batch.trim().toLocaleLowerCase()
  const creator = filters.creator.trim().toLocaleLowerCase()
  const date = task.publish_date?.slice(0, 10) || ''
  return (!batch || [task.task_name, task.batch_code].some(value => (value || '').toLocaleLowerCase().includes(batch))) &&
    (!creator || (task.created_by || '').toLocaleLowerCase().includes(creator)) &&
    (!filters.dateStart || (!!date && date >= filters.dateStart)) &&
    (!filters.dateEnd || (!!date && date <= filters.dateEnd)) &&
    (!filters.planningStatus || manualPlanningLabel(task) === filters.planningStatus) &&
    (!filters.contentStatus || manualContentLabel(task) === filters.contentStatus)
}
