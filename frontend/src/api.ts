import { request } from './api/http'
import { queryManualTasks, queryPlanPage, queryAccountPage, queryPeriodPage, queryPeriodContext, queryResultFailures } from './api/queries'
import type { AccountOption, AccountPlanRecord, AdjustmentRecord, BatchDetail, BatchSummary, ConfigResponse, ConfigVersionSummary, ManualPreviewInput, ManualPreviewResponse, ManualTaskSummary, StrategyConfig, TopicOption } from './types'

export interface TagTaxonomyItem {
  id: string | null; name: string; enabled: boolean
  node_type?: 'group' | 'tag'
  parent_id?: string | null
  client_id?: string
}
export interface TagTaxonomyResponse {
  version: number
  tags: Record<string, string[]>
  items: Record<string, TagTaxonomyItem[]>
}

function tagNameText(value: unknown): string {
  if (typeof value === 'string') return value
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    for (const key of ['name', 'label', 'value', 'title', 'text']) {
      if (key in record) return tagNameText(record[key])
    }
    return JSON.stringify(value)
  }
  return value == null ? '' : String(value)
}

function normalizeTagTaxonomy(value: unknown): TagTaxonomyResponse {
  const response = value && typeof value === 'object' ? value as Record<string, unknown> : {}
  const source = (response.items ?? response.tags) as Record<string, unknown> | undefined
  const items: Record<string, TagTaxonomyItem[]> = {}
  for (const dimension of ['T1', 'T2', 'T3', 'T4', 'T5']) {
    const values = Array.isArray(source?.[dimension]) ? source[dimension] as unknown[] : []
    items[dimension] = values.map(value => {
      if (typeof value === 'string') return { id: null, name: value, enabled: true }
      const item = value && typeof value === 'object' ? value as Record<string, unknown> : {}
      return {
        id: typeof item.id === 'string' ? item.id : null,
        name: tagNameText(item.name ?? item.label ?? item.value),
        enabled: typeof item.enabled === 'boolean' ? item.enabled : true,
        node_type: item.node_type === 'group' ? 'group' as const : 'tag' as const,
        parent_id: typeof item.parent_id === 'string' ? item.parent_id : null,
      }
    }).filter(item => item.name.length > 0)
  }
  const tags = Object.fromEntries(Object.entries(items).map(([dimension, values]) => [
    dimension, values.filter(item => item.enabled && item.node_type !== 'group').map(item => item.name),
  ]))
  return {
    version: typeof response.version === 'number' ? response.version : 0,
    tags,
    items,
  }
}

const post = <T>(path: string, body: Record<string, unknown> = {}) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body) })

async function allManualTasks(path: string): Promise<ManualTaskSummary[]> {
  const tasks = new Map<string, ManualTaskSummary>()
  const limit = 100
  for (let offset = 0; ; offset += limit) {
    const rows = await post<ManualTaskSummary[]>(`${path}/query`, { limit, offset })
    const previousSize = tasks.size
    for (const row of rows) tasks.set(row.task_code, row)
    if (rows.length < limit) return [...tasks.values()]
    if (tasks.size === previousSize) throw new Error('任务分页读取异常，请重试')
  }
}

export const api = {
  health: () => request<{ service: string; database: string }>('/health', { method: 'GET' }),
  config: () => post<ConfigResponse>('/config/query'),
  saveConfig: (config: StrategyConfig, expectedVersion: number) =>
    post<ConfigResponse>('/config/save', { config, expectedVersion }),
  configVersions: () => post<ConfigVersionSummary[]>('/config/versions/query'),
  restoreConfig: (version: number, expectedVersion: number) =>
    post<ConfigResponse>(`/config/versions/${version}/restore`, { expectedVersion }),
  tagTaxonomy: async () => normalizeTagTaxonomy(await post<unknown>('/tag-taxonomy/query')),
  saveTagTaxonomy: async (items: Record<string, TagTaxonomyItem[]>, expectedVersion: number) =>
    normalizeTagTaxonomy(await post<unknown>('/tag-taxonomy/save', { items, expected_version: expectedVersion })),
  accounts: (limit = 1000, includeDisabled = false) => post<AccountOption[]>('/accounts/query', { limit, includeDisabled }),
  manualAccountAvailability: (publishDate: string) => post<import('./types').ManualAccountAvailability>('/manual-plans/account-availability/query', { publishDate }),
  topics: () => post<TopicOption[]>('/topics/query', { limit: 1000 }),
  topicDetail: (topicId: string, topicType?: string | null) => post<TopicOption>(`/topics/${encodeURIComponent(topicId)}/detail/query`, { topicType: topicType || undefined }),
  batches: (type?: 'manual' | 'auto', limit = 200) =>
    post<BatchSummary[]>('/batches/query', { limit, planType: type }),
  batch: (id: number) => post<BatchDetail>(`/batches/${id}/query`),
  replacementCandidates: (itemId: number) => post<TopicOption[]>(`/items/${itemId}/replacement-candidates/query`),
  replaceTopic: (itemId: number, newTopicId: string, expectedVersion: number, reason: string) =>
    request<{ item: AccountPlanRecord; adjustment: AdjustmentRecord }>(`/items/${itemId}/replace-topic`, { method: 'POST', body: JSON.stringify({ new_topic_id: newTopicId, expected_version: expectedVersion, reason }) }),
  adjustments: (itemId: number) => post<AdjustmentRecord[]>(`/items/${itemId}/adjustments/query`),
  previewManual: (input: ManualPreviewInput) =>
    request<ManualPreviewResponse>('/manual-plans/previews', { method: 'POST', body: JSON.stringify(input) }),
  submitManualPreview: (previewId: string) =>
    request<ManualTaskSummary>(`/manual-plans/previews/${encodeURIComponent(previewId)}/submit`, { method: 'POST' }),
  manualTaskPage: queryManualTasks,
  planPage: queryPlanPage,
  accountPage: queryAccountPage,
  periodPage: queryPeriodPage,
  periodContext: queryPeriodContext,
  resultFailures: queryResultFailures,
  manualTasks: () => allManualTasks('/manual-plans/tasks'),
  marketingTasks: () => allManualTasks('/manual-plans/marketing-tasks'),
  createMarketingTask: (input: { request_id: string; task_name: string; topic_id: string; allocation_count: number }) =>
    request<ManualTaskSummary>('/manual-plans/marketing-tasks', { method: 'POST', body: JSON.stringify(input) }),
  marketingTaskDetails: (code: string) => post<{ task: ManualTaskSummary; accounts: AccountOption[]; topics: TopicOption[] }>(`/manual-plans/marketing-tasks/${encodeURIComponent(code)}/query`),
}

