import type { AccountOption, AccountPlanRecord, AdjustmentRecord, AutoCycleSummary, AutoFailure, BatchDetail, BatchSummary, ConfigResponse, ConfigVersionSummary, ManualPlanInput, ManualPreviewInput, ManualPreviewResponse, ManualTaskSummary, PlanningAccountSummary, PlanningCycleSummary, StrategyConfig, TopicOption } from './types'

export interface ContentProductionTask {
  production_task_id: string; slot_id: string; topic_id: string; provider: string
  status: string; content_id: string | null; last_error: string
  accepted_at: string; completed_at: string | null
  request: { planning: { publish_date: string }; account: { account_name: string }; topic: { title: string } }
  response: { title?: string; body?: string }
}

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

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      cache: options.cache ?? 'no-store',
      headers: { 'Content-Type': 'application/json', ...options.headers },
    })
  } catch {
    throw new Error('后端服务尚未连接')
  }
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
    } catch { /* Use the HTTP status. */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

async function allManualTasks(path: string): Promise<ManualTaskSummary[]> {
  const tasks = new Map<string, ManualTaskSummary>()
  const limit = 100
  for (let offset = 0; ; offset += limit) {
    const rows = await request<ManualTaskSummary[]>(`${path}?limit=${limit}&offset=${offset}`)
    const previousSize = tasks.size
    for (const row of rows) tasks.set(row.task_code, row)
    if (rows.length < limit) return [...tasks.values()]
    if (tasks.size === previousSize) throw new Error('任务分页读取异常，请重试')
  }
}

export const api = {
  health: () => request<{ service: string; database: string }>('/health'),
  config: () => request<ConfigResponse>('/config'),
  saveConfig: (config: StrategyConfig, expectedVersion: number) =>
    request<ConfigResponse>(`/config?expected_version=${expectedVersion}`, { method: 'PUT', body: JSON.stringify(config) }),
  configVersions: () => request<ConfigVersionSummary[]>('/config/versions'),
  restoreConfig: (version: number, expectedVersion: number) =>
    request<ConfigResponse>(`/config/versions/${version}/restore?expected_version=${expectedVersion}`, { method: 'POST' }),
  configModuleVersions: (module: 'marketing' | 'strategy') =>
    request<ConfigVersionSummary[]>(`/config/modules/${module}/versions`),
  saveConfigModule: (module: 'marketing' | 'strategy', config: StrategyConfig, expectedVersion: number) =>
    request<ConfigResponse>(`/config/modules/${module}?expected_version=${expectedVersion}`, { method: 'PUT', body: JSON.stringify(config) }),
  restoreConfigModule: (module: 'marketing' | 'strategy', version: number, expectedVersion: number) =>
    request<ConfigResponse>(`/config/modules/${module}/versions/${version}/restore?expected_version=${expectedVersion}`, { method: 'POST' }),
  tagTaxonomy: async () => normalizeTagTaxonomy(await request<unknown>('/tag-taxonomy')),
  saveTagTaxonomy: async (items: Record<string, TagTaxonomyItem[]>, expectedVersion: number) =>
    normalizeTagTaxonomy(await request<unknown>('/tag-taxonomy', { method: 'PUT', body: JSON.stringify({ items, expected_version: expectedVersion }) })),
  accounts: (limit = 1000, includeDisabled = false) => request<AccountOption[]>(`/accounts?limit=${limit}&include_disabled=${includeDisabled}`),
  manualAccountAvailability: (publishDate: string) => request<import('./types').ManualAccountAvailability>(`/manual-plans/account-availability?publish_date=${encodeURIComponent(publishDate)}`),
  topics: () => request<TopicOption[]>('/topics?limit=1000'),
  topicDetail: (topicId: string, topicType?: string | null) => request<TopicOption>(`/topics/${encodeURIComponent(topicId)}/detail${topicType ? `?topic_type=${encodeURIComponent(topicType)}` : ''}`),
  batches: (type?: 'manual' | 'auto', limit = 200) =>
    request<BatchSummary[]>(`/batches?limit=${limit}${type ? `&plan_type=${type}` : ''}`),
  batch: (id: number) => request<BatchDetail>(`/batches/${id}`),
  contentProductionFlow: (id: number) => request<{ batch_id: number; tasks: ContentProductionTask[] }>(`/batches/${id}/content-production`),
  accountItems: (account: string, limit = 5000) => request<AccountPlanRecord[]>(`/items?account=${encodeURIComponent(account)}&limit=${limit}`),
  planningAccounts: () => request<PlanningAccountSummary[]>('/planning-accounts'),
  replacementCandidates: (itemId: number) => request<TopicOption[]>(`/items/${itemId}/replacement-candidates`),
  replaceTopic: (itemId: number, newTopicId: string, expectedVersion: number, reason: string) =>
    request<{ item: AccountPlanRecord; adjustment: AdjustmentRecord }>(`/items/${itemId}/replace-topic`, { method: 'POST', body: JSON.stringify({ new_topic_id: newTopicId, expected_version: expectedVersion, reason }) }),
  adjustments: (itemId: number) => request<AdjustmentRecord[]>(`/items/${itemId}/adjustments`),
  createManual: (input: ManualPlanInput) =>
    request<BatchDetail>('/batches/manual', { method: 'POST', body: JSON.stringify(input) }),
  previewManual: (input: ManualPreviewInput) =>
    request<ManualPreviewResponse>('/manual-plans/previews', { method: 'POST', body: JSON.stringify(input) }),
  submitManualPreview: (previewId: string) =>
    request<ManualTaskSummary>(`/manual-plans/previews/${encodeURIComponent(previewId)}/submit`, { method: 'POST' }),
  manualTasks: () => allManualTasks('/manual-plans/tasks'),
  marketingTasks: () => allManualTasks('/manual-plans/marketing-tasks'),
  createMarketingTask: (input: { request_id: string; task_name: string; topic_id: string; allocation_count: number }) =>
    request<ManualTaskSummary>('/manual-plans/marketing-tasks', { method: 'POST', body: JSON.stringify(input) }),
  marketingTaskDetails: (code: string) => request<{ task: ManualTaskSummary; accounts: AccountOption[]; topics: TopicOption[] }>(`/manual-plans/marketing-tasks/${encodeURIComponent(code)}`),
  planningCycles: () => request<PlanningCycleSummary[]>('/planning-cycles'),
  planningCycleItems: (cycleId: string, limit = 5000) =>
    request<AccountPlanRecord[]>(`/planning-cycles/${encodeURIComponent(cycleId)}/items?limit=${limit}`),
  planningFailures: (cycleId: string) =>
    request<AutoFailure[]>(`/planning-cycles/${encodeURIComponent(cycleId)}/failures`),
  autoCycles: () => request<AutoCycleSummary[]>('/auto-planning/cycles'),
  autoFailures: (cycleId: string) =>
    request<AutoFailure[]>(`/auto-planning/cycles/${encodeURIComponent(cycleId)}/failures`),
}

