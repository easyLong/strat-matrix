import type { AccountOption, AccountPlanRecord, AdjustmentRecord, AutoCycleSummary, AutoFailure, BatchDetail, BatchSummary, ConfigResponse, ConfigVersionSummary, ManualPlanInput, ManualPreviewInput, ManualPreviewResponse, ManualTaskSummary, PlanningAccountSummary, PlanningCycleSummary, StrategyConfig, TopicOption } from './types'

export interface TagTaxonomyItem { id: string | null; name: string; enabled: boolean }
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
      }
    }).filter(item => item.name.length > 0)
  }
  const tags = Object.fromEntries(Object.entries(items).map(([dimension, values]) => [
    dimension, values.filter(item => item.enabled).map(item => item.name),
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
  saveTagTaxonomy: (items: Record<string, TagTaxonomyItem[]>, expectedVersion: number) =>
    request<TagTaxonomyResponse>('/tag-taxonomy', { method: 'PUT', body: JSON.stringify({ items, expected_version: expectedVersion }) }),
  accounts: () => request<AccountOption[]>('/accounts'),
  topics: () => request<TopicOption[]>('/topics?limit=1000'),
  batches: (type?: 'manual' | 'auto', limit = 200) =>
    request<BatchSummary[]>(`/batches?limit=${limit}${type ? `&plan_type=${type}` : ''}`),
  batch: (id: number) => request<BatchDetail>(`/batches/${id}`),
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
  manualTasks: () => request<ManualTaskSummary[]>('/manual-plans/tasks'),
  planningCycles: () => request<PlanningCycleSummary[]>('/planning-cycles'),
  planningCycleItems: (cycleId: string, limit = 5000) =>
    request<AccountPlanRecord[]>(`/planning-cycles/${encodeURIComponent(cycleId)}/items?limit=${limit}`),
  autoCycles: () => request<AutoCycleSummary[]>('/auto-planning/cycles'),
  autoFailures: (cycleId: string) =>
    request<AutoFailure[]>(`/auto-planning/cycles/${encodeURIComponent(cycleId)}/failures`),
}

