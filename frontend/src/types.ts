export interface StageTarget {
  name: string
  traffic: number
  conversion: number
}

export interface LifecycleCondition {
  field: 'valid_content_count' | 'rolling_interaction_count' | 'followers_count'
  operator: 'lt' | 'lte' | 'gte' | 'gt' | 'eq'
  value: number
  join: 'AND' | 'OR'
}

export interface LifecycleRule {
  name: string
  conditions: LifecycleCondition[]
  catchAll: boolean
}

export interface StrategyConfig {
  marketing_max: number
  planning_days: number[]
  schedule_day: number
  schedule_time: string
  hotspot_ratio: number
  rolling_posts: number
  stage_targets: StageTarget[]
  lifecycle_rules: LifecycleRule[]
}

export interface ConfigResponse {
  version: number
  updated_at: string | null
  config: StrategyConfig
  is_demo: boolean
}

export interface ConfigVersionSummary {
  version: number
  action: string
  source_version: number | null
  created_at: string
  created_by: string
  config: StrategyConfig
}

export interface AccountOption {
  account_id: string
  account_name: string
  city: string
  persona: string
  marketing_eligible: boolean
  status: string
  certified: boolean | null
  followers: number | null
  traffic_trend: string
}

export interface TopicOption {
  topic_id: string
  topic_title: string
  category: string
  content_type: string
  outline: string
  is_marketing: boolean
  status: string
}

export interface BatchSummary {
  id: number
  batch_code: string
  plan_type: 'manual' | 'auto'
  status: string
  cycle_start: string
  cycle_end: string
  account_count: number
  content_count: number
  result_count: number
  note: string
  created_at: string
}

export interface PlanItem {
  id: number
  account_id: string
  account_name: string
  publish_date: string
  slot_type: string
  topic_id: string
  topic_title: string
  status: string
  slot_id?: string | null
  production_status?: string | null
  publish_status: string
  allow_replace: boolean
  replace_block_reason: string
  result_version: number | null
  content_type: string
  outline: string
  lifecycle_stage?: string | null
  content_role?: string | null
  topic_type?: 'normal' | 'marketing' | 'hotspot' | null
}

export interface BatchDetail extends BatchSummary {
  items: PlanItem[]
}

export interface AccountPlanRecord extends PlanItem {
  batch_code: string
  plan_type: 'manual' | 'auto'
  cycle_start: string
  cycle_end: string
}

export interface AdjustmentRecord {
  id: number
  item_id: number
  result_version: number
  adjustment_source: string
  old_topic_id: string
  old_topic_title: string
  new_topic_id: string
  new_topic_title: string
  reason: string
  created_at: string
  created_by: string
}

export interface ManualItemInput {
  account_id: string
  account_name: string
  topic_id: string
  topic_title: string
}

export interface ManualPlanInput {
  publish_date: string
  items: ManualItemInput[]
  note: string
}

export interface ManualPreviewInput {
  publish_date: string
  account_ids: string[]
  target_count?: number
  topic_ids: string[]
  note: string
  city?: string
  persona?: string
  keyword?: string
  traffic_trend?: string
  certified?: boolean | null
  followers_min?: number | null
  followers_max?: number | null
}

export interface ManualPreviewResponse {
  preview_id: string
  publish_date: string
  expires_at: string
  items: ManualItemInput[]
  note: string
}

export interface ManualTaskSummary {
  id: number
  task_code: string
  preview_code: string
  publish_date: string
  planned_account_count: number
  result_count: number
  failure_count: number
  topic_count: number
  status: string
  failure_reason: string
  batch_id: number | null
  last_error: string
  created_at: string
  updated_at: string
}

export interface PlanningCycleSummary {
  cycle_id: string
  cycle_start: string
  cycle_end: string
  batch_count: number
  account_count: number
  auto_item_count: number
  manual_item_count: number
  content_count: number
  regular_slots: number
  marketing_slots: number
  hotspot_slots: number
  topic_uses: number
  unique_topics: number
  success_accounts: number
  failed_accounts: number
  updated_at: string
}

export interface AutoCycleSummary {
  cycle_id: string
  cycle_start: string
  cycle_end: string
  batch_count: number
  account_count: number
  success_accounts: number
  failed_accounts: number
  regular_slots: number
  marketing_slots: number
  hotspot_slots: number
  hotspot_submitted: number
  hotspot_pending: number
  status: string
  updated_at: string
}

export interface AutoFailure {
  batch_code: string
  account_id: string | null
  account_name: string
  reason: string
}

