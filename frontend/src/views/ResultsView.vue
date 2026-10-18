<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import TagCascader from '../components/TagCascader.vue'
import TopicDetailDrawer from '../components/TopicDetailDrawer.vue'
import { emptyLabelFilters, matchesLabelFilters, tagGroups, tagNames, type TaxonomyItems } from '../topicTaxonomy'
import AccountTypeBadge from '../components/AccountTypeBadge.vue'
import ListPagination from '../components/ListPagination.vue'
import LoadingSkeleton from '../components/LoadingSkeleton.vue'
import { useDebouncedFields } from '../composables/useDebouncedFields'
import { statusTone } from '../ui/status'
import { formatDateTime } from '../planningTime'
import { api } from '../api'
import { usePlanningStore } from '../store'
import type { AccountOption, AccountPlanRecord, AdjustmentRecord, BatchSummary, PlanningAccountSummary, PlanningCycleSummary, TopicOption } from '../types'

type AccountGroup = { account_id: string; account_name: string; lifecycle_stage: string; items: AccountPlanRecord[] }

const store = usePlanningStore()
const route = useRoute()
const pane = ref<'period' | 'detail' | 'account'>('account')
const accountFiltersExpanded = ref(false)
const batchFiltersExpanded = ref(false)
const accountDetailFiltersExpanded = ref(false)
const batchDetailFiltersExpanded = ref(false)
const planningAccounts = ref<PlanningAccountSummary[]>([])
const accountCatalog = ref<AccountOption[]>([])
const topicCatalog = ref<TopicOption[]>([])
const selectedAccount = ref<AccountGroup | null>(null)
const accountReturnPane = ref<'detail' | 'account'>('detail')
const accountHistoryBatchId = ref('all')
const accountHistoryPlanType = ref<'all' | 'manual' | 'auto'>('all')
const historyAccountKeyword = ref('')
const historyAccountType = ref('')
const historyUmNo = ref('')
const historyOrganization = ref('')
const historyPlatform = ref('')
const historyBusinessLine = ref('')
const historyCity = ref('')
const historyLifecycle = ref('')
const historyFollowersMin = ref<number | null>(null)
const historyFollowersMax = ref<number | null>(null)
const accountHistoryCycleId = ref('all')
const accountHistoryPage = ref(1)
const accountHistoryPageSize = ref(10)
const batchSummaries = ref<BatchSummary[]>([])
const planningCycleSummaries = ref<PlanningCycleSummary[]>([])
const cycleQuery = ref('')
const cycleItems = ref<AccountPlanRecord[]>([])
const selectedBatch = ref<BatchSummary | null>(null)
const cyclePage = ref(1)
const cyclePageSize = ref(10)
const cycleAccountKeyword = ref('')
const cyclePlanType = ref('all')
const cycleDetailPlanType = ref('all')
const cycleContentType = ref('all')
const cyclePlanningStatus = ref('all')
const cycleProductionStatus = ref('all')
const accountListPage = ref(1)
const accountListPageSize = ref(20)
const batchListPage = ref(1)
const batchListPageSize = ref(20)
const error = ref('')
const visibleError = computed(() => error.value
  .split('\uFF1B')
  .filter(message => !/^\s*(?:404\s*:\s*)?not found\s*$/i.test(message))
  .join('\uFF1B'))
const busy = ref(false)
const replaceTarget = ref<AccountPlanRecord | null>(null)
const drawerMode = ref<'view' | 'replace' | 'history'>('replace')
const replacementTopics = ref<TopicOption[]>([])
const taxonomyItems = ref<TaxonomyItems>({})
const labelFilters = ref(emptyLabelFilters())
const detailTopic = ref<TopicOption | null>(null)
const replacementFiltersExpanded = ref(false)
const replacementQuery = ref('')
const replacementTopicIdFilter = ref('')
const replacementMarketingFilter = ref('')
const replacementContentType = ref('')
const replacementProduct = ref('')
const replacementActivity = ref('')
const replacementHotspot = ref('')
const { terms: searchTerms, flush: flushSearch } = useDebouncedFields({ historyAccountKeyword, historyUmNo, cycleQuery, replacementQuery, replacementTopicIdFilter })
const replacementTopicId = ref('')
const replacementReason = ref('')
const adjustmentHistory = ref<AdjustmentRecord[]>([])
const replaceBusy = ref(false)
function monthWeekOf(date: string) {
  const monday = new Date(`${cycleWeekStart(date)}T00:00:00Z`)
  return Math.floor((monday.getUTCDate() - 1) / 7) + 1
}
function cycleWeekStart(date: string) {
  const value = new Date(`${date}T00:00:00Z`)
  value.setUTCDate(value.getUTCDate() - (value.getUTCDay() + 6) % 7)
  return value.toISOString().slice(0, 10)
}
function cycleWeekEnd(date: string) {
  const value = new Date(`${cycleWeekStart(date)}T00:00:00Z`)
  value.setUTCDate(value.getUTCDate() + 6)
  return value.toISOString().slice(0, 10)
}
function cyclePeriodLabel(date: string) {
  const value = new Date(`${cycleWeekStart(date)}T00:00:00Z`)
  return `${value.getUTCFullYear()}\u5e74${value.getUTCMonth() + 1}\u6708\u7b2c${monthWeekOf(date)}\u5468`
}
function scrollAccountWeek(event: MouseEvent, direction: -1 | 1) {
  const viewport = (event.currentTarget as HTMLElement).parentElement?.querySelector<HTMLElement>('.account-week-scroll')
  if (!viewport) return
  viewport.scrollBy({ left: direction * Math.min(480, viewport.clientWidth * 0.75), behavior: 'smooth' })
}
const visibleCycles = computed(() => batchSummaries.value.filter(batch =>
  (!searchTerms.value.cycleQuery.trim() || `${batch.task_name} ${batch.batch_code} ${batch.cycle_start} ${batch.cycle_end}`.toLowerCase().includes(searchTerms.value.cycleQuery.trim().toLowerCase())) &&
  (cyclePlanType.value === 'all' || batch.plan_type === cyclePlanType.value) &&
  (cyclePlanningStatus.value === 'all' || (batch.planning_status || batch.status) === cyclePlanningStatus.value) &&
  (cycleProductionStatus.value === 'all' || (batch.content_status || '') === cycleProductionStatus.value),
))
const cyclePlanningStatuses = computed(() => [...new Set(batchSummaries.value.map(batch => batch.planning_status || batch.status).filter(Boolean))])
const cycleProductionStatuses = computed(() => [...new Set(batchSummaries.value.map(batch => batch.content_status).filter(Boolean))])
const visiblePlanningAccounts = computed(() => historyAccountOptions.value)
const pagedPlanningAccounts = computed(() => visiblePlanningAccounts.value.slice((accountListPage.value - 1) * accountListPageSize.value, accountListPage.value * accountListPageSize.value))
const pagedBatches = computed(() => visibleCycles.value.slice((batchListPage.value - 1) * batchListPageSize.value, batchListPage.value * batchListPageSize.value))
const listLoading = computed(() => !store.initialized || (busy.value && !batchSummaries.value.length && !planningAccounts.value.length))
const filteredCycleItems = computed(() => cycleItems.value.filter(item =>
  (!cycleAccountKeyword.value.trim() || `${item.account_name} ${item.account_id}`.toLocaleLowerCase().includes(cycleAccountKeyword.value.trim().toLocaleLowerCase())) &&
  (cycleDetailPlanType.value === 'all' || item.plan_type === cycleDetailPlanType.value) &&
  (cycleContentType.value === 'all' || item.content_type === cycleContentType.value),
))
function groupAccountRecords(items: AccountPlanRecord[]): AccountGroup[] {
  const groups = new Map<string, AccountGroup>()
  for (const item of items) {
    const group = groups.get(item.account_id)
    if (group) group.items.push(item)
    else groups.set(item.account_id, {
      account_id: item.account_id,
      account_name: item.account_name,
      lifecycle_stage: item.lifecycle_stage || '\u2014',
      items: [item],
    })
  }
  return [...groups.values()]
}
const groupedCycleItems = computed(() => groupAccountRecords(filteredCycleItems.value))
const cyclePageCount = computed(() => Math.max(1, Math.ceil(groupedCycleItems.value.length / cyclePageSize.value)))
const pagedGroupedCycleItems = computed(() => {
  const start = (cyclePage.value - 1) * cyclePageSize.value
  return groupedCycleItems.value.slice(start, start + cyclePageSize.value)
})
const dimensionCycleOptions = computed(() => planningCycleSummaries.value
  .map(cycle => ({ value: cycleWeekStart(cycle.cycle_start), label: cyclePeriodLabel(cycle.cycle_start) }))
  .filter((cycle, index, options) => options.findIndex(item => item.value === cycle.value) === index)
  .sort((a, b) => b.value.localeCompare(a.value)))
const historyOrganizationOptions = computed(() => [...new Set(accountCatalog.value.map(item => item.organization).filter(Boolean))].sort())
const historyPlatformOptions = computed(() => [...new Set(accountCatalog.value.map(item => item.platform).filter(Boolean))].sort())
const historyBusinessLineOptions = computed(() => [...new Set(accountCatalog.value.map(item => item.business_line).filter(Boolean))].sort())
const historyCityOptions = computed(() => [...new Set(accountCatalog.value.map(item => item.city).filter(Boolean))].sort())
const historyLifecycleOptions = computed(() => [...new Set(accountCatalog.value.map(item => item.lifecycle_stage).filter(Boolean))])
const historyAccountOptions = computed(() => {
  const keyword = searchTerms.value.historyAccountKeyword.trim().toLocaleLowerCase()
  const umNo = searchTerms.value.historyUmNo.trim().toLocaleLowerCase()
  const matches = planningAccounts.value.filter(summary => {
    const account = accountCatalog.value.find(item => item.account_id === summary.account_id)
    const accountType = account?.account_type || (account?.certified === true ? '\u8ba4\u8bc1' : account?.certified === false ? '\u975e\u8ba4\u8bc1' : '')
    return (!keyword || `${summary.account_name} ${account?.account_alias ?? ''} ${summary.account_id}`.toLocaleLowerCase().includes(keyword)) &&
      (!historyAccountType.value || accountType === historyAccountType.value) &&
      (!umNo || (account?.um_no ?? '').toLocaleLowerCase().includes(umNo)) &&
      (!historyOrganization.value || account?.organization === historyOrganization.value) &&
      (!historyPlatform.value || account?.platform === historyPlatform.value) &&
      (!historyBusinessLine.value || account?.business_line === historyBusinessLine.value) &&
      (!historyCity.value || account?.city === historyCity.value) &&
      (!historyLifecycle.value || account?.lifecycle_stage === historyLifecycle.value) &&
      (historyFollowersMin.value === null || (account?.followers != null && account.followers >= historyFollowersMin.value)) &&
      (historyFollowersMax.value === null || (account?.followers != null && account.followers <= historyFollowersMax.value))
  })
  if (selectedAccount.value && !matches.some(item => item.account_id === selectedAccount.value?.account_id)) {
    const current = planningAccounts.value.find(item => item.account_id === selectedAccount.value?.account_id)
    if (current) matches.unshift(current)
  }
  return matches
})
watch(() => [searchTerms.value.historyAccountKeyword, searchTerms.value.historyUmNo, historyAccountType.value, historyOrganization.value, historyPlatform.value, historyBusinessLine.value, historyCity.value, historyLifecycle.value, historyFollowersMin.value, historyFollowersMax.value, accountListPageSize.value, planningAccounts.value, accountCatalog.value], () => { accountListPage.value = 1 })
watch([visibleCycles, batchListPageSize], () => { batchListPage.value = 1 })
const filteredAccountHistory = computed(() => {
  if (!selectedAccount.value) return []
  return selectedAccount.value.items.filter(item =>
    (accountHistoryBatchId.value === 'all' || item.batch_id === Number(accountHistoryBatchId.value)) &&
    (accountHistoryPlanType.value === 'all' || item.plan_type === accountHistoryPlanType.value) &&
    (accountHistoryCycleId.value === 'all' || cycleWeekStart(item.cycle_start) === accountHistoryCycleId.value),
  )
})
watch([cycleAccountKeyword, cycleDetailPlanType, cycleContentType, cyclePageSize], () => { cyclePage.value = 1 })
watch(cyclePageCount, pageCount => { if (cyclePage.value > pageCount) cyclePage.value = pageCount })
const accountHistoryGroups = computed(() => {
  const groups = new Map<string, {
    cycle_start: string
    cycle_end: string
    items: AccountPlanRecord[]
  }>()
  for (const item of filteredAccountHistory.value) {
    const key = cycleWeekStart(item.publish_date)
    const group = groups.get(key)
    if (group) group.items.push(item)
    else groups.set(key, {
      cycle_start: key,
      cycle_end: cycleWeekEnd(key),
      items: [item],
    })
  }
  return [...groups.values()]
    .map(group => ({ ...group, items: group.items.sort((a, b) => a.publish_date.localeCompare(b.publish_date) || a.id - b.id) }))
    .sort((a, b) => b.cycle_start.localeCompare(a.cycle_start))
})
const accountHistoryPageCount = computed(() => Math.max(1, Math.ceil(accountHistoryGroups.value.length / accountHistoryPageSize.value)))
const pagedAccountHistoryGroups = computed(() => {
  const start = (accountHistoryPage.value - 1) * accountHistoryPageSize.value
  return accountHistoryGroups.value.slice(start, start + accountHistoryPageSize.value)
})
watch([accountHistoryCycleId, accountHistoryBatchId, accountHistoryPlanType, accountHistoryPageSize], () => { accountHistoryPage.value = 1 })
watch(accountHistoryPageCount, pageCount => { if (accountHistoryPage.value > pageCount) accountHistoryPage.value = pageCount })
const cycleContentTypes = computed(() => [...new Set(cycleItems.value.map(item => item.content_type).filter(Boolean))])
const dimensionContentTypes = computed(() => [...new Set([...topicCatalog.value.map(topic => topic.content_type), ...cycleContentTypes.value].filter(Boolean))].sort())
const accountDetailBatchOptions = computed(() => {
  if (!selectedAccount.value) return []
  const batches = new Map<number, { id: number; label: string }>()
  for (const item of selectedAccount.value.items) {
    if (!batches.has(item.batch_id)) {
      const batch = batchSummaries.value.find(candidate => candidate.id === item.batch_id)
      batches.set(item.batch_id, {
        id: item.batch_id,
        label: batch ? `${batch.task_name} · ${batch.cycle_start}` : `${item.batch_code} · ${item.cycle_start}`,
      })
    }
  }
  return [...batches.values()].sort((a, b) => b.id - a.id)
})

function getAccountProfile(accountId: string) { return accountCatalog.value.find(account => account.account_id === accountId) }
function accountTypeLabel(accountId: string) {
  const profile = getAccountProfile(accountId)
  return profile?.account_type || (profile?.certified === true ? '\u8ba4\u8bc1' : profile?.certified === false ? '\u975e\u8ba4\u8bc1' : '\u2014')
}
function followersLabel(accountId: string) {
  const followers = getAccountProfile(accountId)?.followers
  return followers == null ? '\u2014' : new Intl.NumberFormat('zh-CN').format(followers)
}
function slotLabel(slotType: string, planType: string) {
  if (planType === 'manual') return '手动追加'
  return ({ regular: '\u666e\u901a', marketing_priority: '\u8425\u9500', hotspot: '\u70ed\u70b9', manual_extra: '\u624b\u52a8\u8ffd\u52a0' } as Record<string, string>)[slotType] ?? slotType
}
function plannedSlotLabel(item: AccountPlanRecord) {
  return ({ regular: '\u666e\u901a', marketing_priority: '\u8425\u9500', hotspot: '\u70ed\u70b9', manual_extra: '\u624b\u52a8\u8ffd\u52a0' } as Record<string, string>)[item.slot_type]
    ?? (item.plan_type === 'manual' ? '\u624b\u52a8\u8ffd\u52a0' : '\u666e\u901a')
}
function statusTagClass(status: string) {
  return statusTone(status)
}
function topicTypeLabel(item: AccountPlanRecord) {
  if (!item.topic_id) return '\u5f85\u786e\u5b9a'
  const type = String(item.topic_type ?? '')
  if (type === '\u8425\u9500' || type === 'marketing' || type === 'marketing_priority') return '\u8425\u9500'
  if (type === '\u70ed\u70b9' || type === 'hotspot') return '\u70ed\u70b9'
  if (type === '\u666e\u901a' || type === 'normal' || type === 'regular') return '\u666e\u901a'
  return item.slot_type === 'hotspot' ? '\u70ed\u70b9' : item.slot_type === 'marketing_priority' ? '\u8425\u9500' : '\u666e\u901a'
}
function productionStatusLabel(item: AccountPlanRecord) {
  return ({ ready: '\u751f\u4ea7\u4e2d', generated: '\u5df2\u751f\u6210', published: '\u5df2\u53d1\u5e03', failed: '\u751f\u4ea7\u5931\u8d25' } as Record<string, string>)[item.production_status ?? ''] ?? item.publish_status
}
function weekdayLabel(date: string) {
  return new Intl.DateTimeFormat('zh-CN', { weekday: 'short', timeZone: 'UTC' }).format(new Date(`${date}T00:00:00Z`))
}
function accountWeekDays(history: { cycle_start: string; items: AccountPlanRecord[] }) {
  const start = new Date(`${cycleWeekStart(history.cycle_start)}T00:00:00Z`)
  return Array.from({ length: 7 }, (_, offset) => {
    const date = new Date(start)
    date.setUTCDate(start.getUTCDate() + offset)
    const value = date.toISOString().slice(0, 10)
    return {
      date: value,
      dateLabel: value.slice(5),
      weekday: weekdayLabel(value),
      items: history.items.filter(item => item.publish_date === value),
    }
  })
}

const replacementContentTypes = computed(() => [...new Set(replacementTopics.value.map(topic => topic.content_type).filter(Boolean))].sort())
const replacementProducts = computed(() => [...new Set(replacementTopics.value.map(topic => topic.related_product).filter(Boolean))].sort())
const replacementActivities = computed(() => [...new Set(replacementTopics.value.map(topic => topic.related_activity).filter(Boolean))].sort())
const replacementHotspots = computed(() => [...new Set(replacementTopics.value.map(topic => topic.related_hotspot).filter(Boolean))].sort())
const replacementCandidates = computed(() => replacementTopics.value.filter(topic =>
  (!searchTerms.value.replacementTopicIdFilter.trim() || topic.topic_id === searchTerms.value.replacementTopicIdFilter.trim()) &&
  (!searchTerms.value.replacementQuery.trim() || topic.topic_title.toLocaleLowerCase().includes(searchTerms.value.replacementQuery.trim().toLocaleLowerCase())) &&
  (!replacementMarketingFilter.value || String(topic.is_marketing) === replacementMarketingFilter.value) &&
  (!replacementContentType.value || topic.content_type === replacementContentType.value) &&
  (!replacementProduct.value || topic.related_product === replacementProduct.value) &&
  (!replacementActivity.value || topic.related_activity === replacementActivity.value) &&
  (!replacementHotspot.value || topic.related_hotspot === replacementHotspot.value) &&
  matchesLabelFilters(topic, labelFilters.value, taxonomyItems.value),
))
function replacementTopicType(topic: TopicOption) {
  return topic.topic_type || (topic.is_marketing ? '\u8425\u9500' : '\u666e\u901a')
}
async function openReplacement(item: AccountPlanRecord) {
  drawerMode.value = 'replace'
  replaceTarget.value = item
  replacementFiltersExpanded.value = false
  labelFilters.value = emptyLabelFilters()
  replacementQuery.value = ''
  replacementTopicIdFilter.value = ''
  replacementMarketingFilter.value = ''
  replacementContentType.value = ''
  replacementProduct.value = ''
  replacementActivity.value = ''
  replacementHotspot.value = ''
  replacementTopicId.value = ''
  replacementReason.value = ''
  adjustmentHistory.value = []
  try {
    const [topics, history, taxonomy] = await Promise.all([api.replacementCandidates(item.id), api.adjustments(item.id), api.tagTaxonomy()])
    taxonomyItems.value = taxonomy.items
    replacementTopics.value = topics
    adjustmentHistory.value = history
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '读取替换信息失败' }
}
async function showCurrentTopicDetails(item: AccountPlanRecord) {
  detailTopic.value = topicCatalog.value.find(topic => topic.topic_id === item.topic_id) ?? { topic_id: item.topic_id, topic_title: item.topic_title, outline: item.outline, content_type: item.content_type, category: '', is_marketing: item.topic_type === '营销', status: '可用', topic_type: item.topic_type === '营销' ? '营销' : item.topic_type === '热点' ? '热点' : '普通' }
  try { taxonomyItems.value = (await api.tagTaxonomy()).items } catch { /* Existing topic paths remain readable. */ }
}
function openPlanDetails(item: AccountPlanRecord) {
  drawerMode.value = 'view'
  replaceTarget.value = item
  replacementTopics.value = []
  adjustmentHistory.value = []
}
async function openAdjustmentHistory(item: AccountPlanRecord) {
  drawerMode.value = 'history'
  replaceTarget.value = item
  replacementTopics.value = []
  replacementQuery.value = ''
  replacementTopicId.value = ''
  replacementReason.value = ''
  adjustmentHistory.value = []
  try {
    adjustmentHistory.value = await api.adjustments(item.id)
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '读取调整记录失败' }
}
function closeReplacement() { replaceTarget.value = null }
async function confirmReplacement() {
  if (!replaceTarget.value || !replacementTopicId.value || replaceTarget.value.result_version === null) return
  replaceBusy.value = true
  error.value = ''
  try {
    const result = await api.replaceTopic(replaceTarget.value.id, replacementTopicId.value, replaceTarget.value.result_version, replacementReason.value.trim())
    const update = (rows: AccountPlanRecord[]) => rows.map(row => row.id === result.item.id ? result.item : row)
    cycleItems.value = update(cycleItems.value)
    if (selectedAccount.value) selectedAccount.value = { ...selectedAccount.value, items: update(selectedAccount.value.items) }
    replaceTarget.value = result.item
    adjustmentHistory.value = await api.adjustments(result.item.id)
    replacementTopicId.value = ''
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '替换失败，当前结果未改变' }
  finally { replaceBusy.value = false }
}
function openAccountDetail(group: AccountGroup) {
  accountReturnPane.value = 'detail'
  pane.value = 'account'
  void loadAccountHistory(group)
}
function openPlanningAccount(account: PlanningAccountSummary) {
  accountReturnPane.value = 'account'
  pane.value = 'account'
  void loadAccountHistory(account)
}
function changeAccountDetailBatch(batchId: string) {
  accountHistoryBatchId.value = batchId
  const batch = batchSummaries.value.find(item => item.id === Number(batchId))
  if (batch) {
    accountHistoryCycleId.value = cycleWeekStart(batch.cycle_start)
  } else {
    accountHistoryCycleId.value = 'all'
  }
}
function returnFromAccountDetail() {
  selectedAccount.value = null
  pane.value = accountReturnPane.value
}
async function loadBatch(batchId: number, planType?: 'manual' | 'auto') {
  if (!store.databaseReady) return
  busy.value = true
  error.value = ''
  try {
    const batch = await api.batch(batchId)
    selectedBatch.value = batch
    batchDetailFiltersExpanded.value = false
    cyclePage.value = 1
    cycleAccountKeyword.value = ''
    cycleItems.value = batch.items.map(item => ({
      ...item,
      batch_id: batch.id,
      batch_code: batch.batch_code,
      batch_created_at: batch.created_at,
      plan_type: batch.plan_type,
      cycle_start: batch.cycle_start,
      cycle_end: batch.cycle_end,
    }))
    cycleDetailPlanType.value = batch.plan_type
    if (planType) cyclePlanType.value = planType
    pane.value = 'detail'
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '\u8bfb\u53d6\u6279\u6b21\u5931\u8d25' }
  finally { busy.value = false }
}
async function loadAccountHistory(group: AccountGroup | PlanningAccountSummary) {
  accountDetailFiltersExpanded.value = false
  accountHistoryPlanType.value = 'all'
  if (accountReturnPane.value === 'detail' && selectedBatch.value) {
    accountHistoryBatchId.value = String(selectedBatch.value.id)
    accountHistoryCycleId.value = cycleWeekStart(selectedBatch.value.cycle_start)
  } else {
    accountHistoryBatchId.value = 'all'
    accountHistoryCycleId.value = 'all'
  }
  selectedAccount.value = { account_id: group.account_id, account_name: group.account_name, lifecycle_stage: 'lifecycle_stage' in group ? group.lifecycle_stage : '\u2014', items: [] }
  accountHistoryPage.value = 1
  pane.value = 'account'
  busy.value = true
  error.value = ''
  try {
    const history = await api.accountItems(group.account_id)
    selectedAccount.value = {
      account_id: group.account_id,
      account_name: group.account_name,
      lifecycle_stage: 'lifecycle_stage' in group ? group.lifecycle_stage : '\u2014',
      items: history,
    }
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '读取账号历史失败' }
  finally { busy.value = false }
}
async function loadPlanningAccountsFromCycles(cycles: PlanningCycleSummary[]): Promise<PlanningAccountSummary[]> {
  const cycleRows = await Promise.all(cycles.map(cycle => api.planningCycleItems(cycle.cycle_id, 5000)))
  const groups = new Map<string, {
    account_id: string
    account_name: string
    account_owner: string
    cycles: Set<string>
    slot_count: number
    latest_cycle_start: string
    latest_cycle_updated_at: string | null
    latest_status: string
    latest_batch_id: number | null
  }>()
  for (const items of cycleRows) {
    for (const item of items) {
      const cycleStart = cycleWeekStart(item.cycle_start)
      let group = groups.get(item.account_id)
      if (!group) {
        group = {
          account_id: item.account_id,
          account_name: item.account_name,
          account_owner: '',
          cycles: new Set<string>(),
          slot_count: 0,
          latest_cycle_start: cycleStart,
          latest_cycle_updated_at: item.batch_created_at,
          latest_status: item.status,
          latest_batch_id: item.batch_id ?? null,
        }
        groups.set(item.account_id, group)
      }
      group.cycles.add(cycleStart)
      group.slot_count += 1
      if (cycleStart > group.latest_cycle_start) group.latest_cycle_start = cycleStart
      if (item.batch_created_at && (!group.latest_cycle_updated_at || item.batch_created_at > group.latest_cycle_updated_at)) {
        group.latest_cycle_updated_at = item.batch_created_at
        group.latest_status = item.status
        group.latest_batch_id = item.batch_id ?? null
      }
    }
  }
  return [...groups.values()]
    .map(({ cycles: accountCycles, ...account }) => ({ ...account, cycle_count: accountCycles.size }))
    .sort((a, b) => (b.latest_cycle_updated_at ?? '').localeCompare(a.latest_cycle_updated_at ?? '') || a.account_name.localeCompare(b.account_name, 'zh-CN'))
}
async function refresh() {
  busy.value = true
  error.value = ''
  try {
    const [batchesResult, cyclesResult, accountsResult, accountCatalogResult, topicCatalogResult] = await Promise.allSettled([
      api.batches(undefined, 5000),
      api.planningCycles(),
      api.planningAccounts(),
      api.accounts(1000, true),
      api.topics(),
    ])
    const failures: string[] = []
    if (batchesResult.status === 'fulfilled') batchSummaries.value = batchesResult.value
    else failures.push(batchesResult.reason instanceof Error ? batchesResult.reason.message : '读取结果定位信息失败')
    if (cyclesResult.status === 'fulfilled') planningCycleSummaries.value = cyclesResult.value
    else failures.push(cyclesResult.reason instanceof Error ? cyclesResult.reason.message : '读取批次周期失败')
    if (accountsResult.status === 'fulfilled') planningAccounts.value = accountsResult.value
    else if (cyclesResult.status === 'fulfilled') {
      try { planningAccounts.value = await loadPlanningAccountsFromCycles(cyclesResult.value) }
      catch (exc) { failures.push(exc instanceof Error ? exc.message : '读取参与账号失败') }
    } else failures.push(accountsResult.reason instanceof Error ? accountsResult.reason.message : '读取参与账号失败')
    if (accountCatalogResult.status === 'fulfilled') accountCatalog.value = accountCatalogResult.value
    if (topicCatalogResult.status === 'fulfilled') topicCatalog.value = topicCatalogResult.value
    if (failures.length) error.value = failures.join('\uFF1B')
  }
  catch (exc) { error.value = exc instanceof Error ? exc.message : '加载失败' }
  finally { busy.value = false }
}


watch(() => [route.query.batch, route.query.plan_type, batchSummaries.value.length] as const, async ([id, planType, count]) => {
  if (!count || typeof id !== 'string' || !/^\d+$/.test(id)) return
  await loadBatch(Number(id), planType === 'manual' || planType === 'auto' ? planType : undefined)
}, { immediate: true })
watch(() => store.databaseReady, ready => { if (ready) void refresh() }, { immediate: true })
</script>

<template>
  <div class="page-head"><div><h1>&#x7B56;&#x5212;&#x7ED3;&#x679C;</h1></div></div>
  <div v-if="visibleError" class="banner error-banner" role="alert">{{ visibleError }}</div>
  <div v-if="pane !== 'detail' && !selectedAccount" class="result-tabs" role="group" aria-label="策划结果查看维度"><button type="button" :class="{ active: pane === 'account' }" :aria-pressed="pane === 'account'" @click="pane = 'account'">账号维度</button><button type="button" :class="{ active: pane === 'period' }" :aria-pressed="pane === 'period'" @click="pane = 'period'">批次维度</button></div>
  <section v-if="listLoading" class="card"><LoadingSkeleton /></section>
  <section v-if="pane === 'period' && !listLoading" class="card">
    <div class="card-body batch-dimension-filters">
      <button class="filter-collapse-toggle" type="button" aria-controls="batch-dimension-filter-fields" :aria-expanded="batchFiltersExpanded" @click="batchFiltersExpanded = !batchFiltersExpanded"><span>&#x7B5B;&#x9009;&#x6761;&#x4EF6;</span><svg :class="{ expanded: batchFiltersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg></button>
      <div id="batch-dimension-filter-fields" v-show="batchFiltersExpanded" class="batch-filter-fields">
        <div class="batch-filter-caption">&#x6279;&#x6B21;&#x7B5B;&#x9009;</div>
        <div class="batch-filter-row">
          <input v-model="cycleQuery" type="search" placeholder="&#x6279;&#x6B21;&#x540D;&#x79F0;&#x3001;&#x7F16;&#x53F7;&#x6216;&#x5468;&#x671F;" @keydown.enter.prevent="flushSearch" />
          <select v-model="cyclePlanType"><option value="all">&#x5168;&#x90E8;&#x7B56;&#x5212;&#x65B9;&#x5F0F;</option><option value="auto">&#x81EA;&#x52A8;&#x7B56;&#x5212;</option><option value="manual">&#x624B;&#x52A8;&#x7B56;&#x5212;</option></select>
          <select v-model="cyclePlanningStatus"><option value="all">&#x5168;&#x90E8;&#x7B56;&#x5212;&#x72B6;&#x6001;</option><option v-for="value in cyclePlanningStatuses" :key="value" :value="value">{{ value }}</option></select>
          <select v-model="cycleProductionStatus"><option value="all">&#x5168;&#x90E8;&#x5185;&#x5BB9;&#x72B6;&#x6001;</option><option v-for="value in cycleProductionStatuses" :key="value" :value="value">{{ value }}</option></select>
        </div>
      </div>
    </div>
    <div class="table-wrap"><table><thead><tr><th>&#x6279;&#x6B21;</th><th>&#x7B56;&#x5212;&#x65B9;&#x5F0F;</th><th>&#x6279;&#x6B21;&#x5468;&#x671F;</th><th>&#x8D26;&#x53F7;&#x6570;</th><th>&#x5B8C;&#x6210;&#x6570;</th><th>&#x5931;&#x8D25;&#x6570;</th><th>&#x9009;&#x9898;&#x6570;</th><th>&#x7B56;&#x5212;&#x72B6;&#x6001;</th><th>&#x5185;&#x5BB9;&#x72B6;&#x6001;</th><th>&#x66F4;&#x65B0;&#x65F6;&#x95F4;</th><th>&#x64CD;&#x4F5C;</th></tr></thead><tbody>
      <tr v-for="batch in pagedBatches" :key="batch.id"><td><div class="account-name-cell"><b>{{ batch.task_name || '\u2014' }}</b><small>ID {{ batch.batch_code }}</small></div></td><td>{{ batch.plan_type === 'manual' ? '\u624b\u52a8\u7b56\u5212' : '\u81ea\u52a8\u7b56\u5212' }}</td><td>{{ batch.cycle_start }} &#x81F3; {{ batch.cycle_end }}</td><td>{{ batch.account_count }}</td><td class="batch-count" :class="{ completed: batch.completed_count > 0 }">{{ batch.completed_count }}</td><td class="batch-count" :class="{ failed: batch.failed_count > 0 }">{{ batch.failed_count }}</td><td>{{ batch.topic_count }}</td><td><span :class="['tag', statusTagClass(batch.planning_status)]">{{ batch.planning_status || batch.status }}</span></td><td><span :class="['tag', statusTagClass(batch.content_status)]">{{ batch.content_status || '\u2014' }}</span></td><td>{{ formatDateTime(batch.updated_at || batch.created_at) }}</td><td><button class="text-btn" type="button" @click="loadBatch(batch.id)">&#x67E5;&#x770B;&#x8BE6;&#x60C5;</button></td></tr>
      <tr v-if="visibleCycles.length === 0"><td colspan="11"><div class="empty-state"><b>&#x6682;&#x65E0;&#x7B56;&#x5212;&#x6279;&#x6B21;</b></div></td></tr>
    </tbody></table></div>
    <ListPagination v-model:page="batchListPage" v-model:page-size="batchListPageSize" :total="visibleCycles.length" unit="个批次" class="list-pagination-inset" />
  </section>
  <section v-if="pane === 'detail'" class="card">
    <div class="card-head"><div><h2>&#x6279;&#x6B21;&#x8BE6;&#x60C5;</h2><small v-if="selectedBatch">{{ selectedBatch.batch_code }} &#xB7; {{ selectedBatch.cycle_start }} &#x81F3; {{ selectedBatch.cycle_end }}</small></div><button class="btn" type="button" @click="pane = 'period'">&#x8FD4;&#x56DE;&#x6279;&#x6B21;&#x7EF4;&#x5EA6;</button></div>
    <LoadingSkeleton v-if="busy" :rows="8" />
    <template v-else-if="selectedBatch">
    <div class="card-body filter-collapse-row"><button class="filter-collapse-toggle" type="button" aria-controls="batch-detail-filter-fields" :aria-expanded="batchDetailFiltersExpanded" @click="batchDetailFiltersExpanded = !batchDetailFiltersExpanded"><span>&#x7B5B;&#x9009;&#x6761;&#x4EF6;</span><svg :class="{ expanded: batchDetailFiltersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg></button></div>
    <div id="batch-detail-filter-fields" v-show="batchDetailFiltersExpanded" class="card-body detail-filter-fields">
      <label><span>&#x8D26;&#x53F7; ID &#x6216;&#x6635;&#x79F0;</span><input v-model="cycleAccountKeyword" type="search" placeholder="&#x8F93;&#x5165;&#x8D26;&#x53F7; ID &#x6216;&#x6635;&#x79F0;" /></label>
      <label><span>&#x7B56;&#x5212;&#x65B9;&#x5F0F;</span><select v-model="cycleDetailPlanType"><option value="all">&#x5168;&#x90E8;</option><option value="auto">&#x81EA;&#x52A8;&#x7B56;&#x5212;</option><option value="manual">&#x624B;&#x52A8;&#x7B56;&#x5212;</option></select></label>
      <label><span>&#x5185;&#x5BB9;&#x7C7B;&#x578B;</span><select v-model="cycleContentType"><option value="all">&#x5168;&#x90E8;&#x5185;&#x5BB9;&#x7C7B;&#x578B;</option><option v-for="value in dimensionContentTypes" :key="value" :value="value">{{ value }}</option></select></label>
    </div>
    <div v-if="groupedCycleItems.length" class="batch-account-list planning-account-groups">
      <article v-for="group in pagedGroupedCycleItems" :key="group.account_id" class="batch-account-card planning-account-group">
        <div class="batch-account-head planning-account-group-head">
          <div><div class="batch-account-name"><button class="account-detail-link" type="button" @click="openAccountDetail(group)">{{ group.account_name }}</button><span class="tag gray">{{ group.account_id }}</span><span v-if="group.lifecycle_stage && group.lifecycle_stage !== ''" class="tag purple">{{ group.lifecycle_stage }}</span></div></div>
          <div class="batch-account-head-actions"><span class="tag blue">{{ group.items.length }} &#x6761;&#x7B56;&#x5212;</span></div>
        </div>
        <div class="account-week-carousel"><button class="account-week-scroll-control previous" type="button" aria-label="&#x5411;&#x5DE6;&#x6ED1;&#x52A8;&#x5468;&#x5386;" @click="scrollAccountWeek($event, -1)"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m12 4-6 6 6 6" /></svg></button><div class="account-week-scroll"><div class="account-week-calendar">
          <section v-for="day in accountWeekDays({ cycle_start: selectedBatch.cycle_start, items: group.items })" :key="day.date" class="account-week-day">
            <header class="account-week-day-head"><div><b>{{ day.dateLabel }}</b><small>{{ day.weekday }}</small></div><span>{{ day.items.length }} 条</span></header>
            <div v-if="day.items.length" class="account-week-day-items">
              <article v-for="record in day.items" :key="record.id" class="account-week-plan-card" role="button" tabindex="0" @click="openPlanDetails(record)" @keydown.enter="openPlanDetails(record)">
                <div class="account-week-plan-tags"><span class="tag gray">{{ record.plan_type === 'manual' ? '\u624B\u52A8\u7B56\u5212' : '\u81EA\u52A8\u7B56\u5212' }}</span><span :class="['tag', statusTagClass(productionStatusLabel(record))]">{{ productionStatusLabel(record) }}</span></div>
                <h3>{{ record.topic_title }}</h3>
                <div class="account-week-plan-meta"><span>{{ record.content_type || '\u2014' }}</span><span>{{ topicTypeLabel(record) }}</span></div>
              </article>
            </div>
            <div v-else class="account-week-day-empty">&#x6682;&#x65E0;&#x8BA1;&#x5212;</div>
          </section>
        </div></div><button class="account-week-scroll-control next" type="button" aria-label="&#x5411;&#x53F3;&#x6ED1;&#x52A8;&#x5468;&#x5386;" @click="scrollAccountWeek($event, 1)"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m8 4 6 6-6 6" /></svg></button></div>
      </article>
      <ListPagination v-model:page="cyclePage" v-model:page-size="cyclePageSize" :total="groupedCycleItems.length" unit="个账号" />
    </div>
    <div v-else class="empty-state"><b>&#x5F53;&#x524D;&#x7B5B;&#x9009;&#x6761;&#x4EF6;&#x4E0B;&#x6682;&#x65E0;&#x7B56;&#x5212;&#x8BB0;&#x5F55;</b></div>
    </template>
  </section>

  <section v-if="pane === 'account' && !listLoading" class="card">
    <template v-if="selectedAccount">
      <div class="card-head"><div><h2>账号详情</h2><small>{{ selectedAccount.account_name }} · {{ selectedAccount.account_id }}</small></div><button class="btn" type="button" @click="returnFromAccountDetail">{{ accountReturnPane === 'detail' ? '返回批次详情' : '返回账号列表' }}</button></div>
      <div class="card-body filter-collapse-row"><button class="filter-collapse-toggle" type="button" aria-controls="account-detail-filter-fields" :aria-expanded="accountDetailFiltersExpanded" @click="accountDetailFiltersExpanded = !accountDetailFiltersExpanded"><span>&#x7B5B;&#x9009;&#x6761;&#x4EF6;</span><svg :class="{ expanded: accountDetailFiltersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg></button></div>
      <div id="account-detail-filter-fields" v-show="accountDetailFiltersExpanded" class="card-body detail-filter-fields">
        <label><span>&#x6279;&#x6B21;</span><select v-model="accountHistoryBatchId" @change="changeAccountDetailBatch(accountHistoryBatchId)"><option value="all">&#x5168;&#x90E8;&#x6279;&#x6B21;</option><option v-for="batch in accountDetailBatchOptions" :key="batch.id" :value="String(batch.id)">{{ batch.label }}</option></select></label>
        <label><span>&#x7B56;&#x5212;&#x65B9;&#x5F0F;</span><select v-model="accountHistoryPlanType"><option value="all">&#x5168;&#x90E8;</option><option value="auto">&#x81EA;&#x52A8;&#x7B56;&#x5212;</option><option value="manual">&#x624B;&#x52A8;&#x7B56;&#x5212;</option></select></label>
      </div>
      <LoadingSkeleton v-if="busy" :rows="8" />
      <div v-else-if="accountHistoryGroups.length" class="batch-account-list">

        <article v-for="history in pagedAccountHistoryGroups" :key="history.cycle_start" class="batch-account-card account-history-batch">
          <div class="batch-account-head account-history-batch-head"><div><b>{{ cyclePeriodLabel(history.cycle_start) }} · {{ history.cycle_start }} 至{{ history.cycle_end }}</b></div><span class="tag blue">{{ history.items.length }} 条策划</span></div>
          <div class="account-week-carousel"><button class="account-week-scroll-control previous" type="button" aria-label="&#x5411;&#x5DE6;&#x6ED1;&#x52A8;&#x5468;&#x5386;" @click="scrollAccountWeek($event, -1)"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m12 4-6 6 6 6" /></svg></button><div class="account-week-scroll"><div class="account-week-calendar">
            <section v-for="day in accountWeekDays(history)" :key="day.date" class="account-week-day">
              <header class="account-week-day-head"><div><b>{{ day.dateLabel }}</b><small>{{ day.weekday }}</small></div><span>{{ day.items.length }} 条</span></header>
              <div v-if="day.items.length" class="account-week-day-items">
                <article v-for="record in day.items" :key="record.id" class="account-week-plan-card" role="button" tabindex="0" @click="openPlanDetails(record)" @keydown.enter="openPlanDetails(record)">
                  <div class="account-week-plan-tags"><span class="tag gray">{{ record.plan_type === 'manual' ? '手动策划' : '自动策划' }}</span><span :class="['tag', statusTagClass(productionStatusLabel(record))]">{{ productionStatusLabel(record) }}</span></div>
                  <h3>{{ record.topic_title }}</h3>
                  <div class="account-week-plan-meta"><span>{{ record.content_type || '\u2014' }}</span><span>{{ topicTypeLabel(record) }}</span></div>
                </article>
              </div>
              <div v-else class="account-week-day-empty">暂无计划</div>
            </section>
          </div></div><button class="account-week-scroll-control next" type="button" aria-label="&#x5411;&#x53F3;&#x6ED1;&#x52A8;&#x5468;&#x5386;" @click="scrollAccountWeek($event, 1)"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m8 4 6 6-6 6" /></svg></button></div>
        </article>
        <ListPagination v-model:page="accountHistoryPage" v-model:page-size="accountHistoryPageSize" :total="accountHistoryGroups.length" unit="周" />
      </div>
      <div v-else class="empty-state"><b>当前筛选范围内暂无策划数据</b></div>
    </template>
    <template v-else>
      <div class="card-body filter-collapse-row"><button class="filter-collapse-toggle" type="button" aria-controls="account-dimension-filter-fields" :aria-expanded="accountFiltersExpanded" @click="accountFiltersExpanded = !accountFiltersExpanded"><span>&#x7B5B;&#x9009;&#x6761;&#x4EF6;</span><svg :class="{ expanded: accountFiltersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg></button></div>
      <div id="account-dimension-filter-fields" v-show="accountFiltersExpanded" class="card-body account-history-toolbar">
        <label><span>&#x8D26;&#x53F7; ID &#x6216;&#x6635;&#x79F0;</span><input v-model="historyAccountKeyword" type="search" placeholder="&#x8F93;&#x5165;&#x8D26;&#x53F7; ID &#x6216;&#x6635;&#x79F0;" @keydown.enter.prevent="flushSearch" /></label>
        <label><span>&#x5C5E;&#x4E3B; UM &#x53F7;</span><input v-model="historyUmNo" type="search" placeholder="&#x8F93;&#x5165;&#x5C5E;&#x4E3B; UM &#x53F7;" @keydown.enter.prevent="flushSearch" /></label>
        <label><span>&#x8D26;&#x53F7;&#x7C7B;&#x578B;</span><select v-model="historyAccountType"><option value="">&#x5168;&#x90E8;</option><option value="&#x8BA4;&#x8BC1;">&#x8BA4;&#x8BC1;</option><option value="&#x975E;&#x8BA4;&#x8BC1;">&#x975E;&#x8BA4;&#x8BC1;</option></select></label>
        <label><span>&#x5C5E;&#x4E3B;&#x7EC4;&#x7EC7;</span><select v-model="historyOrganization"><option value="">&#x5168;&#x90E8;</option><option v-for="item in historyOrganizationOptions" :key="item" :value="item">{{ item }}</option></select></label>
        <label><span>&#x5E73;&#x53F0;</span><select v-model="historyPlatform"><option value="">&#x5168;&#x90E8;</option><option v-for="item in historyPlatformOptions" :key="item" :value="item">{{ item }}</option></select></label>
        <label><span>&#x4E1A;&#x52A1;&#x7EBF;</span><select v-model="historyBusinessLine"><option value="">&#x5168;&#x90E8;</option><option v-for="item in historyBusinessLineOptions" :key="item" :value="item">{{ item }}</option></select></label>
        <label><span>&#x5730;&#x57DF;</span><select v-model="historyCity"><option value="">&#x5168;&#x90E8;</option><option v-for="item in historyCityOptions" :key="item" :value="item">{{ item }}</option></select></label>
        <label><span>&#x751F;&#x547D;&#x5468;&#x671F;</span><select v-model="historyLifecycle"><option value="">&#x5168;&#x90E8;</option><option v-for="item in historyLifecycleOptions" :key="item" :value="item">{{ item }}</option></select></label>
        <label><span>&#x7C89;&#x4E1D;&#x91CF;</span><div class="account-history-follower-range"><input v-model.number="historyFollowersMin" type="number" min="0" placeholder="&#x8D77;&#x59CB;&#x7C89;&#x4E1D;&#x91CF;" /><i>&#x81F3;</i><input v-model.number="historyFollowersMax" type="number" min="0" placeholder="&#x622A;&#x6B62;&#x7C89;&#x4E1D;&#x91CF;" /></div></label>
        <label><span>&#x6279;&#x6B21;&#x5468;&#x671F;</span><select v-model="accountHistoryCycleId"><option value="all">&#x5168;&#x90E8;&#x5468;&#x671F;</option><option v-for="cycle in dimensionCycleOptions" :key="cycle.value" :value="cycle.value">{{ cycle.label }}</option></select></label>
      </div>

      <div class="table-wrap"><table><thead><tr><th>&#x8D26;&#x53F7;</th><th>&#x8D26;&#x53F7;&#x7C7B;&#x578B;</th><th>&#x5C5E;&#x4E3B; UM &#x53F7;</th><th>&#x5C5E;&#x4E3B;&#x7EC4;&#x7EC7;</th><th>&#x4E1A;&#x52A1;&#x7EBF;</th><th>&#x5E73;&#x53F0;</th><th>&#x5730;&#x57DF;</th><th>&#x751F;&#x547D;&#x5468;&#x671F;</th><th>&#x7C89;&#x4E1D;&#x91CF;</th><th>&#x7B56;&#x5212;&#x7ED3;&#x679C;</th><th>&#x8D26;&#x53F7;&#x72B6;&#x6001;</th></tr></thead><tbody>
        <tr v-for="account in pagedPlanningAccounts" :key="account.account_id"><td><div class="account-name-cell"><b>{{ account.account_name }}</b><small>{{ account.account_id }}</small></div></td><td><AccountTypeBadge :type="accountTypeLabel(account.account_id)" /></td><td>{{ getAccountProfile(account.account_id)?.um_no || '\u2014' }}</td><td>{{ getAccountProfile(account.account_id)?.organization || account.account_owner || '\u2014' }}</td><td>{{ getAccountProfile(account.account_id)?.business_line || '\u2014' }}</td><td>{{ getAccountProfile(account.account_id)?.platform || '\u2014' }}</td><td>{{ getAccountProfile(account.account_id)?.city || '\u2014' }}</td><td>{{ getAccountProfile(account.account_id)?.lifecycle_stage || '\u2014' }}</td><td>{{ followersLabel(account.account_id) }}</td><td><button class="text-btn" type="button" @click="openPlanningAccount(account)">&#x67E5;&#x770B;&#x7B56;&#x5212;&#x7ED3;&#x679C;</button></td><td><span :class="['tag', getAccountProfile(account.account_id)?.status === '\u542f\u7528' ? 'green' : 'gray']">{{ getAccountProfile(account.account_id)?.status || '\u2014' }}</span></td></tr>
        <tr v-if="visiblePlanningAccounts.length === 0"><td colspan="11"><div class="empty-state">{{ planningAccounts.length ? '\u6ca1\u6709\u5339\u914d\u7684\u8d26\u53f7' : '\u6682\u65e0\u53c2\u4e0e\u7b56\u5212\u7684\u8d26\u53f7' }}</div></td></tr>
      </tbody></table></div>
      <ListPagination v-model:page="accountListPage" v-model:page-size="accountListPageSize" :total="visiblePlanningAccounts.length" unit="个账号" class="list-pagination-inset" />
    </template>
  </section>
  <div v-if="replaceTarget" class="drawer-mask" @click.self="closeReplacement">
    <aside class="drawer" role="dialog" aria-modal="true" :aria-label="drawerMode === 'view' ? String.fromCharCode(35745,21010,35814,24773) : drawerMode === 'replace' ? String.fromCharCode(26367,25442,36873,39064) : String.fromCharCode(26597,30475,35843,25972,35760,24405)">
      <div class="drawer-head"><div><small>{{ drawerMode === 'view' ? String.fromCharCode(35745,21010,35814,24773) : drawerMode === 'replace' ? String.fromCharCode(26367,25442,36873,39064) : String.fromCharCode(26597,30475,35843,25972,35760,24405) }}</small><h2>{{ replaceTarget.account_name }}</h2></div><button class="icon-btn" type="button" aria-label="&#20851;&#38381;" @click="closeReplacement">&times;</button></div>
      <div class="drawer-body">
        <template v-if="drawerMode === 'view'">
          <section class="plan-detail-section"><h3>内容计划详情</h3><p>本条计划执行所需的信息</p>
            <div class="detail-grid"><div><small>投放日期</small><b>{{ replaceTarget.publish_date }} &middot; {{ weekdayLabel(replaceTarget.publish_date) }}</b></div><div><small>内容支柱</small><b>{{ replaceTarget.content_role || '\u2014' }}</b></div><div><small>内容类型</small><b>{{ replaceTarget.content_type || '\u2014' }}</b></div><div><small>执行方式</small><b>{{ replaceTarget.plan_type === 'manual' ? '手动策划' : 'AI 自动' }}</b></div><div><small>生产状态</small><b>{{ productionStatusLabel(replaceTarget) }}</b></div><div><small>发布状态</small><b>{{ replaceTarget.publish_status }}</b></div></div>
            <div class="plan-detail-topic"><button v-if="replaceTarget.topic_id" class="text-btn" type="button" @click="showCurrentTopicDetails(replaceTarget)">查看选题详情</button><small>选题</small><b>{{ replaceTarget.topic_title || '待定' }}</b><p>{{ replaceTarget.outline || '\u2014' }}</p></div>
          </section>
          <details class="plan-basis-details"><summary>排期依据与关联记录</summary><div class="detail-grid"><div><small>槽位类型</small><b>{{ slotLabel(replaceTarget.slot_type, replaceTarget.plan_type) }}</b></div><div><small>经营阶段</small><b>{{ replaceTarget.lifecycle_stage || '\u2014' }}</b></div><div><small>批次编号</small><b>{{ replaceTarget.batch_code }}</b></div><div><small>选题编号</small><b>{{ replaceTarget.topic_id || '\u2014' }}</b></div></div></details>
        </template>
        <template v-else>
        <div class="detail-note"><b>&#x5F53;&#x524D;&#x9009;&#x9898;:</b>{{ replaceTarget.topic_title }}<br /><b>&#x6295;&#x653E;&#x65E5;&#x671F;:</b>{{ replaceTarget.publish_date }}<br /><b>&#x7C7B;&#x578B;:</b>{{ slotLabel(replaceTarget.slot_type, replaceTarget.plan_type) }}<br /><b>&#x72B6;&#x6001;:</b>{{ replaceTarget.publish_status }}</div>
        <template v-if="drawerMode === 'replace' && replaceTarget.allow_replace">
          <h3>选择新选题</h3>
          <div class="replacement-filter-collapse-row"><button class="filter-collapse-toggle" type="button" aria-controls="replacement-topic-filters" :aria-expanded="replacementFiltersExpanded" @click="replacementFiltersExpanded = !replacementFiltersExpanded"><span>筛选条件</span><svg :class="{ expanded: replacementFiltersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg></button></div>
          <div id="replacement-topic-filters" v-show="replacementFiltersExpanded" class="replacement-topic-filters">
            <label class="field"><span class="field-label-with-tip">选题 ID <span class="field-help-tip" tabindex="0" title="输入完整选题 ID，进行精确匹配">?</span></span><input v-model="replacementTopicIdFilter" type="text" inputmode="text" autocomplete="off" placeholder="输入完整选题 ID" @keydown.enter.prevent="flushSearch" /></label>
            <label class="field"><span class="field-label-with-tip">选题标题 <span class="field-help-tip" tabindex="0" title="输入标题关键词，进行模糊搜索">?</span></span><input v-model="replacementQuery" type="search" placeholder="输入选题标题关键词" @keydown.enter.prevent="flushSearch" /></label>
            <label class="field"><span>选题类型</span><select v-model="replacementMarketingFilter"><option value="">全部</option><option value="true">营销</option><option value="false">非营销</option></select></label>
            <label class="field"><span>内容类型</span><select v-model="replacementContentType"><option value="">全部</option><option v-for="value in replacementContentTypes" :key="value" :value="value">{{ value }}</option></select></label>
            <label class="field"><span>关联产品</span><select v-model="replacementProduct"><option value="">全部</option><option v-for="value in replacementProducts" :key="value" :value="value">{{ value }}</option></select></label>
            <label class="field"><span>关联活动</span><select v-model="replacementActivity"><option value="">全部</option><option v-for="value in replacementActivities" :key="value" :value="value">{{ value }}</option></select></label>
            <label class="field"><span>关联属地热点</span><select v-model="replacementHotspot"><option value="">全部</option><option v-for="value in replacementHotspots" :key="value" :value="value">{{ value }}</option></select></label>
            <div v-for="dimension in (['T3', 'T4', 'T5'] as const)" :key="dimension" class="field"><span>{{ tagNames[dimension] }}</span><TagCascader v-model="labelFilters[dimension]" :groups="tagGroups(taxonomyItems, dimension)" :label="tagNames[dimension]" /></div>
            <button class="text-btn replacement-filter-clear" type="button" @click="replacementTopicIdFilter = ''; replacementQuery = ''; replacementMarketingFilter = ''; replacementContentType = ''; replacementProduct = ''; replacementActivity = ''; replacementHotspot = ''; labelFilters = emptyLabelFilters()">清空筛选</button>
          </div>
          <div class="replacement-topic-count">符合条件 {{ replacementCandidates.length }} 个选题</div>
          <div class="topic-check-list"><label v-for="topic in replacementCandidates" :key="topic.topic_id" class="topic-check"><input v-model="replacementTopicId" type="radio" :value="topic.topic_id" name="replacement-topic" /><span><button class="topic-title-link" type="button" @click.prevent.stop="detailTopic = topic">{{ topic.topic_title }}</button><small>{{ topic.topic_id }}<template v-if="topic.content_type"> · {{ topic.content_type }}</template><template v-if="topic.valid_to"> · 有效至 {{ topic.valid_to.slice(0, 10) }}</template></small><small class="replacement-topic-outline"><b>选题大纲</b>{{ topic.outline || '暂无选题大纲' }}</small></span></label></div>
          <div v-if="replacementCandidates.length === 0" class="empty-state">没有可用候选选题</div>
          <label class="field"><span>替换原因（可选）</span><select v-model="replacementReason"><option value="">请选择原因</option><option>原选题与账号不匹配</option><option>选题重复</option><option>内容方向不合适</option><option>业务临时调整</option><option>其他</option></select></label>
        </template>
        <div v-else-if="drawerMode === 'replace'" class="detail-note">{{ replaceTarget.replace_block_reason || '\u5F53\u524D\u8BB0\u5F55\u6682\u4E0D\u53EF\u66FF\u6362' }}</div>

        <h3>调整记录</h3>
        <div v-if="adjustmentHistory.length === 0" class="empty-state">暂无历史调整</div>
        <div v-for="record in adjustmentHistory" :key="record.id" class="detail-note">{{ formatDateTime(record.created_at) }} · {{ record.created_by }} · {{ record.adjustment_source }}<br />{{ record.old_topic_title }} · {{ record.new_topic_title }}<span v-if="record.reason"> · {{ record.reason }}</span></div>
        </template>
        <div class="footer-actions"><button class="btn" type="button" @click="closeReplacement">&#x5173;&#x95ED;</button><template v-if="drawerMode === 'view'"><button class="btn" type="button" @click="openAdjustmentHistory(replaceTarget)">&#x67E5;&#x770B;&#x8C03;&#x6574;&#x8BB0;&#x5F55;</button><button class="btn" type="button" disabled title="&#x91CD;&#x65B0;&#x751F;&#x6210;&#x63A5;&#x53E3;&#x5C1A;&#x672A;&#x63A5;&#x5165;">&#x91CD;&#x65B0;&#x751F;&#x6210;&#x672C;&#x6761;&#x7B56;&#x5212;</button><button v-if="replaceTarget.allow_replace" class="btn primary" type="button" @click="openReplacement(replaceTarget)">&#x66FF;&#x6362;&#x9009;&#x9898;</button></template><button v-else-if="drawerMode === 'replace' && replaceTarget.allow_replace" class="btn primary" type="button" :disabled="replaceBusy || !replacementTopicId" @click="confirmReplacement">{{ replaceBusy ? '\u4fdd\u5b58\u4e2d\u2026' : '\u786e\u8ba4\u66ff\u6362' }}</button></div>
      </div>
    </aside>
  </div>
  <TopicDetailDrawer v-if="detailTopic" :topic="detailTopic" :items="taxonomyItems" @close="detailTopic = null" />
</template>

<style scoped>
.topic-title-link{padding:0;border:0;background:transparent;color:var(--primary-600);font-size:13px;font-weight:500;text-align:left;line-height:1.6}.topic-title-link:hover{text-decoration:underline}.plan-detail-topic>.text-btn{float:right;font-size:12px}.replacement-topic-filters .field{width:100%}
</style>
