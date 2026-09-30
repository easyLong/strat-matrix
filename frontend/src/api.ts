import type { AccountOption, AccountPlanRecord, AdjustmentRecord, AutoCycleSummary, AutoFailure, BatchDetail, BatchSummary, ConfigResponse, ConfigVersionSummary, ManualPlanInput, ManualPreviewInput, ManualPreviewResponse, ManualTaskSummary, PlanningCycleSummary, StrategyConfig, TopicOption } from './types'

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...options,
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
  tagTaxonomy: () => request<{ version: number; tags: Record<string, string[]> }>('/tag-taxonomy'),
  saveTagTaxonomy: (tags: Record<string, string[]>) =>
    request<{ version: number; tags: Record<string, string[]> }>('/tag-taxonomy', { method: 'PUT', body: JSON.stringify({ tags }) }),
  accounts: () => request<AccountOption[]>('/accounts'),
  topics: () => request<TopicOption[]>('/topics?limit=1000'),
  batches: (type?: 'manual' | 'auto') =>
    request<BatchSummary[]>(`/batches?limit=200${type ? `&plan_type=${type}` : ''}`),
  batch: (id: number) => request<BatchDetail>(`/batches/${id}`),
  accountItems: (account: string, limit = 5000) => request<AccountPlanRecord[]>(`/items?account=${encodeURIComponent(account)}&limit=${limit}`),
  replaceTopic: (itemId: number, newTopicId: string, expectedVersion: number, reason: string) =>
    request<{ item: AccountPlanRecord; adjustment: AdjustmentRecord }>(`/items/${itemId}/replace-topic`, { method: 'POST', body: JSON.stringify({ new_topic_id: newTopicId, expected_version: expectedVersion, reason }) }),
  adjustments: (itemId: number) => request<AdjustmentRecord[]>(`/items/${itemId}/adjustments`),
  createManual: (input: ManualPlanInput) =>
    request<BatchDetail>('/batches/manual', { method: 'POST', body: JSON.stringify(input) }),
  previewManual: (input: ManualPreviewInput) =>
    request<ManualPreviewResponse>('/manual-plans/previews', { method: 'POST', body: JSON.stringify(input) }),
  submitManualPreview: (previewId: string) =>
    request<BatchDetail>(`/manual-plans/previews/${encodeURIComponent(previewId)}/submit`, { method: 'POST' }),
  manualTasks: () => request<ManualTaskSummary[]>('/manual-plans/tasks'),
  planningCycles: () => request<PlanningCycleSummary[]>('/planning-cycles'),
  planningCycleItems: (cycleId: string) =>
    request<AccountPlanRecord[]>(`/planning-cycles/${encodeURIComponent(cycleId)}/items`),
  autoCycles: () => request<AutoCycleSummary[]>('/auto-planning/cycles'),
  autoFailures: (cycleId: string) =>
    request<AutoFailure[]>(`/auto-planning/cycles/${encodeURIComponent(cycleId)}/failures`),
}

