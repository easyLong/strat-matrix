import type { AccountOption, AccountPlanRecord, ManualTaskSummary } from '../types'
import type { ContentTypeCount } from '../ui/contentTypeStats'
import type { ManualTaskFilters } from '../ui/manualTask'
import { request } from './http'

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface PageQuery<F = Record<string, unknown>> {
  page: number
  page_size: number
  filters: F
}

export function queryManualTasks(query: PageQuery<ManualTaskFilters>, signal?: AbortSignal) {
  return request<PageResult<ManualTaskSummary>>('/query/manual-tasks', {
    method: 'POST', body: JSON.stringify(query), signal,
  })
}

export interface PlanPageQuery extends PageQuery {
  mode: 'account' | 'cycle' | 'batch' | 'all'
  account_ids?: string[]
  batch_ids?: number[]
  account_id?: string
  batch_id?: number
  cycle_start?: string
  cycle_end?: string
}
export interface PlanPageResult extends PageResult<AccountPlanRecord> {
  accounts: AccountOption[]
  summary: { accounts: number; batches: number; topics: number }
  distribution: ContentTypeCount[]
  content_types: string[]
}
export function queryPlanPage(query: PlanPageQuery, signal?: AbortSignal) {
  return request<PlanPageResult>('/query/plans', { method: 'POST', body: JSON.stringify(query), signal })
}

export function queryAccountPage(query: PageQuery, signal?: AbortSignal) {
  return request<PageResult<import('../types').PlanningAccountSummary & { profile?: AccountOption }> & { facets: { organizations:string[];platforms:string[];lifecycles:string[] } }>('/query/accounts',{method:'POST',body:JSON.stringify(query),signal})
}
export interface PeriodSummary {
  cycleStart:string;cycleEnd:string;batches:import('../types').BatchSummary[];autoBatches:import('../types').BatchSummary[];manualBatches:import('../types').BatchSummary[];
  autoAccountCount:number;manualAccountCount:number;accountCount:number;completedCount:number;failedCount:number;contentCompletedAccountCount:number;updatedAt:string|null
}
export function queryPeriodPage(query: PageQuery,signal?: AbortSignal) {
  return request<PageResult<PeriodSummary>>('/query/periods',{method:'POST',body:JSON.stringify(query),signal})
}
export function queryPeriodContext(query: Record<string,unknown>) {
  return request<PeriodSummary[]>('/query/period-context',{method:'POST',body:JSON.stringify(query)})
}
export function queryResultFailures(query:PlanPageQuery,signal?:AbortSignal) {
  return request<import('../types').AutoFailure[]>('/query/failures',{method:'POST',body:JSON.stringify(query),signal})
}
