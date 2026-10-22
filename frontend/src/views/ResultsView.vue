<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import TopicDetailDrawer from '../components/TopicDetailDrawer.vue'
import { topicLabels, type TaxonomyItems } from '../topicTaxonomy'
import AccountTypeBadge from '../components/AccountTypeBadge.vue'
import ListPagination from '../components/ListPagination.vue'
import LoadingSkeleton from '../components/LoadingSkeleton.vue'
import ContentProgress from '../components/ContentProgress.vue'
import FloatingTableScrollbar from '../components/FloatingTableScrollbar.vue'
import { useDebouncedFields } from '../composables/useDebouncedFields'
import { statusTone } from '../ui/status'
import { canReplacePlanTopic, productionStatusLabel } from '../ui/slotContentStatus'
import { formatDateTime } from '../planningTime'
import { api } from '../api'
import { usePlanningStore } from '../store'
import type { AccountOption, AccountPlanRecord, AdjustmentRecord, BatchSummary, PlanningAccountSummary, PlanningCycleSummary, TopicOption } from '../types'

type AccountGroup = { account_id: string; account_name: string; lifecycle_stage: string; items: AccountPlanRecord[] }
type SlotOperationLog = { key: string; createdAt: string; action: string; actor: string; detail: string }

const props = withDefaults(defineProps<{
  detailOnly?: boolean
  plan?: AccountPlanRecord | null
  profiles?: AccountOption[]
  externalNavigation?: boolean
}>(), { detailOnly: false, plan: null, profiles: () => [], externalNavigation: false })
const emit = defineEmits<{
  closePlan: []
  planUpdated: [item: AccountPlanRecord]
  viewPlans: [account: PlanningAccountSummary]
}>()

const store = usePlanningStore()
const route = useRoute()
const pane = ref<'period' | 'detail' | 'account'>('account')
const accountTableScroll = ref<HTMLElement | null>(null)
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
const historyLifecycle = ref('')
const historyFollowersMin = ref<number | null>(null)
const historyFollowersMax = ref<number | null>(null)
const appliedAccountFilters = ref({ keyword: '', accountType: '', umNo: '', organization: '', platform: '', lifecycle: '', followersMin: null as number | null, followersMax: null as number | null })
const accountHistoryCycleId = ref('all')
const accountHistoryPage = ref(1)
const accountHistoryPageSize = ref(10)
const appliedAccountDetailFilters = ref({ batchId: 'all', planType: 'all', cycleId: 'all' })
const batchSummaries = ref<BatchSummary[]>([])
const planningCycleSummaries = ref<PlanningCycleSummary[]>([])
const batchYear = ref('all')
const batchMonth = ref('all')
const batchWeek = ref('all')
const appliedBatchFilters = ref({ year: 'all', month: 'all', week: 'all' })
const cycleItems = ref<AccountPlanRecord[]>([])
const selectedBatch = ref<BatchSummary | null>(null)
const expandedBatchAccountIds = ref(new Set<string>())
const cyclePage = ref(1)
const cyclePageSize = ref(10)
const cycleAccountKeyword = ref('')
const cycleDetailPlanType = ref('all')
const cycleContentType = ref('all')
const appliedBatchDetailFilters = ref({ keyword: '', planType: 'all', contentType: 'all' })
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
const planDrawerBody = ref<HTMLElement | null>(null)
const drawerMode = ref<'view' | 'replace' | 'history'>('replace')
const planTopicDetail = ref<TopicOption | null>(null)
const planDetailLoading = ref(false)
const planOperationsLoading = ref(false)
const planOperationsError = ref('')
const replacementTopics = ref<TopicOption[]>([])
const taxonomyItems = ref<TaxonomyItems>({})
const detailTopic = ref<TopicOption | null>(null)
const replacementFiltersExpanded = ref(false)
const replacementQuery = ref('')
const replacementTopicIdFilter = ref('')
const replacementMarketingFilter = ref('')
const replacementContentType = ref('')
const replacementProduct = ref('')
const replacementActivity = ref('')
const replacementHotspot = ref('')
const appliedReplacementFilters = ref({ topicId: '', query: '', marketing: '', contentType: '', product: '', activity: '', hotspot: '' })
const { terms: searchTerms, flush: flushSearch } = useDebouncedFields({ historyAccountKeyword, historyUmNo, replacementQuery, replacementTopicIdFilter })
const replacementTopicId = ref('')
const replacementReason = ref('')
const adjustmentHistory = ref<AdjustmentRecord[]>([])
const replaceBusy = ref(false)
let planDetailRequest = 0
let replacementReturnsToDetails = false
let replacementReturnScrollTop = 0
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
const batchYearOptions = computed(() => [...new Set(batchSummaries.value.map(batch => batch.cycle_start.slice(0, 4)).filter(Boolean))].sort((a, b) => b.localeCompare(a)))
const batchMonthOptions = computed(() => [...new Set(batchSummaries.value
  .filter(batch => batchYear.value === 'all' || batch.cycle_start.slice(0, 4) === batchYear.value)
  .map(batch => batch.cycle_start.slice(5, 7)).filter(Boolean))].sort())
const batchWeekOptions = computed(() => [...new Set(batchSummaries.value
  .filter(batch => (batchYear.value === 'all' || batch.cycle_start.slice(0, 4) === batchYear.value) && (batchMonth.value === 'all' || batch.cycle_start.slice(5, 7) === batchMonth.value))
  .map(batch => monthWeekOf(batch.cycle_start)))].sort((a, b) => a - b))
const visibleCycles = computed(() => batchSummaries.value.filter(batch =>
  (appliedBatchFilters.value.year === 'all' || batch.cycle_start.slice(0, 4) === appliedBatchFilters.value.year) &&
  (appliedBatchFilters.value.month === 'all' || batch.cycle_start.slice(5, 7) === appliedBatchFilters.value.month) &&
  (appliedBatchFilters.value.week === 'all' || String(monthWeekOf(batch.cycle_start)) === appliedBatchFilters.value.week),
))
const visiblePlanningAccounts = computed(() => historyAccountOptions.value)
const pagedPlanningAccounts = computed(() => visiblePlanningAccounts.value.slice((accountListPage.value - 1) * accountListPageSize.value, accountListPage.value * accountListPageSize.value))
const pagedBatches = computed(() => visibleCycles.value.slice((batchListPage.value - 1) * batchListPageSize.value, batchListPage.value * batchListPageSize.value))
const listLoading = computed(() => !store.initialized || (busy.value && !batchSummaries.value.length && !planningAccounts.value.length))
const filteredCycleItems = computed(() => cycleItems.value.filter(item =>
  (!appliedBatchDetailFilters.value.keyword.trim() || `${item.account_name} ${item.account_id}`.toLocaleLowerCase().includes(appliedBatchDetailFilters.value.keyword.trim().toLocaleLowerCase())) &&
  (appliedBatchDetailFilters.value.planType === 'all' || item.plan_type === appliedBatchDetailFilters.value.planType) &&
  (appliedBatchDetailFilters.value.contentType === 'all' || item.content_type === appliedBatchDetailFilters.value.contentType),
))
function applyBatchFilters() {
  appliedBatchFilters.value = { year: batchYear.value, month: batchMonth.value, week: batchWeek.value }
  batchListPage.value = 1
}
function applyBatchDetailFilters() {
  appliedBatchDetailFilters.value = { keyword: cycleAccountKeyword.value, planType: cycleDetailPlanType.value, contentType: cycleContentType.value }
  cyclePage.value = 1
}
function applyAccountFilters() {
  flushSearch()
  appliedAccountFilters.value = { keyword: historyAccountKeyword.value, accountType: historyAccountType.value, umNo: historyUmNo.value, organization: historyOrganization.value, platform: historyPlatform.value, lifecycle: historyLifecycle.value, followersMin: historyFollowersMin.value, followersMax: historyFollowersMax.value }
  accountListPage.value = 1
}
function applyAccountDetailFilters() {
  changeAccountDetailBatch(accountHistoryBatchId.value)
  appliedAccountDetailFilters.value = { batchId: accountHistoryBatchId.value, planType: accountHistoryPlanType.value, cycleId: accountHistoryCycleId.value }
  accountHistoryPage.value = 1
}
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
const batchDashboard = computed(() => {
  const items = cycleItems.value
  const isHotspot = (item: AccountPlanRecord) => item.slot_type === 'hotspot'
  const isMarketing = (item: AccountPlanRecord) => item.slot_type === 'marketing_priority'
  return {
    accountCount: new Set(items.map(item => item.account_id)).size,
    totalPlanningCount: items.length,
    hotspotCount: items.filter(isHotspot).length,
    marketingCount: items.filter(isMarketing).length,
    regularCount: items.filter(item => !isHotspot(item) && !isMarketing(item)).length,
    hotspotPendingCount: items.filter(item => isHotspot(item) && !item.topic_id).length,
  }
})
const cyclePageCount = computed(() => Math.max(1, Math.ceil(groupedCycleItems.value.length / cyclePageSize.value)))
const pagedGroupedCycleItems = computed(() => {
  const start = (cyclePage.value - 1) * cyclePageSize.value
  return groupedCycleItems.value.slice(start, start + cyclePageSize.value)
})
const historyOrganizationOptions = computed(() => [...new Set(accountCatalog.value.map(item => item.organization).filter(Boolean))].sort())
const historyPlatformOptions = computed(() => [...new Set(accountCatalog.value.map(item => item.platform).filter(Boolean))].sort())
const historyLifecycleOptions = computed(() => [...new Set(accountCatalog.value.map(item => item.lifecycle_stage).filter(Boolean))])
const historyAccountOptions = computed(() => {
  const filters = appliedAccountFilters.value
  const keyword = filters.keyword.trim().toLocaleLowerCase()
  const umNo = filters.umNo.trim().toLocaleLowerCase()
  const matches = planningAccounts.value.filter(summary => {
    const account = accountCatalog.value.find(item => item.account_id === summary.account_id)
    const accountType = account?.account_type || (account?.certified === true ? '\u8ba4\u8bc1' : account?.certified === false ? '\u975e\u8ba4\u8bc1' : '')
    return (!keyword || `${summary.account_name} ${account?.account_alias ?? ''} ${summary.account_id}`.toLocaleLowerCase().includes(keyword)) &&
      (!filters.accountType || accountType === filters.accountType) &&
      (!umNo || (account?.um_no ?? '').toLocaleLowerCase().includes(umNo)) &&
      (!filters.organization || account?.organization === filters.organization) &&
      (!filters.platform || account?.platform === filters.platform) &&
      (!filters.lifecycle || account?.lifecycle_stage === filters.lifecycle) &&
      (filters.followersMin === null || (account?.followers != null && account.followers >= filters.followersMin)) &&
      (filters.followersMax === null || (account?.followers != null && account.followers <= filters.followersMax))
  })
  if (selectedAccount.value && !matches.some(item => item.account_id === selectedAccount.value?.account_id)) {
    const current = planningAccounts.value.find(item => item.account_id === selectedAccount.value?.account_id)
    if (current) matches.unshift(current)
  }
  return matches
})
watch([accountListPageSize, planningAccounts, accountCatalog], () => { accountListPage.value = 1 })
watch([visibleCycles, batchListPageSize], () => { batchListPage.value = 1 })
watch(batchYear, () => { batchMonth.value = 'all'; batchWeek.value = 'all' })
watch(batchMonth, () => { batchWeek.value = 'all' })
const filteredAccountHistory = computed(() => {
  if (!selectedAccount.value) return []
  return selectedAccount.value.items.filter(item =>
    (appliedAccountDetailFilters.value.batchId === 'all' || item.batch_id === Number(appliedAccountDetailFilters.value.batchId)) &&
    (appliedAccountDetailFilters.value.planType === 'all' || item.plan_type === appliedAccountDetailFilters.value.planType) &&
    (appliedAccountDetailFilters.value.cycleId === 'all' || cycleWeekStart(item.cycle_start) === appliedAccountDetailFilters.value.cycleId),
  )
})
watch(cyclePageSize, () => { cyclePage.value = 1 })
watch(cyclePageCount, pageCount => { if (cyclePage.value > pageCount) cyclePage.value = pageCount })
const accountHistoryGroups = computed(() => {
  const groups = new Map<number, AccountPlanRecord[]>()
  for (const item of filteredAccountHistory.value) {
    const items = groups.get(item.batch_id)
    if (items) items.push(item)
    else groups.set(item.batch_id, [item])
  }
  return [...groups.entries()].map(([batchId, items]) => {
    const latest = items[0]
    const batch = batchSummaries.value.find(candidate => candidate.id === batchId)
    items.sort((a, b) => b.publish_date.localeCompare(a.publish_date) || b.id - a.id)
    return {
      batch_id: batchId,
      batch_code: latest.batch_code,
      task_name: batch?.task_name || latest.batch_code,
      plan_type: latest.plan_type,
      cycle_start: batch?.cycle_start || latest.cycle_start,
      cycle_end: batch?.cycle_end || latest.cycle_end,
      created_at: batch?.created_at || latest.batch_created_at || '',
      items,
    }
  }).sort((a, b) => b.created_at.localeCompare(a.created_at) || b.batch_id - a.batch_id)
})
const accountHistoryPageCount = computed(() => Math.max(1, Math.ceil(accountHistoryGroups.value.length / accountHistoryPageSize.value)))
const pagedAccountHistoryGroups = computed(() => {
  const start = (accountHistoryPage.value - 1) * accountHistoryPageSize.value
  return accountHistoryGroups.value.slice(start, start + accountHistoryPageSize.value)
})
watch(accountHistoryPageSize, () => { accountHistoryPage.value = 1 })
watch(accountHistoryPageCount, pageCount => { if (accountHistoryPage.value > pageCount) accountHistoryPage.value = pageCount })
const cycleContentTypes = computed(() => [...new Set(cycleItems.value.map(item => item.content_type).filter(Boolean))])
const dimensionContentTypes = computed(() => [...new Set([...topicCatalog.value.map(topic => topic.content_type), ...cycleContentTypes.value].filter(Boolean))].sort())
const planTopicTagGroups = computed(() => {
  if (!planTopicDetail.value) return []
  const labels = topicLabels(planTopicDetail.value, taxonomyItems.value)
  const paths = (nodes: { name: string; path: string[] }[]) => nodes.map(node => node.path.join(' / '))
  return [
    { name: '业务属性', values: [labels.business] },
    { name: '经营作用', values: [labels.role] },
    { name: '内容主题', values: paths([...(labels.primary ? [labels.primary] : []), ...labels.related]) },
    { name: '目标客群', values: paths(labels.audience) },
    { name: '使用场景', values: paths(labels.scenes) },
    { name: '用户需求', values: [labels.need] },
  ].map(group => ({ ...group, values: group.values.filter(Boolean) }))
})
const planOperationLogs = computed<SlotOperationLog[]>(() => {
  const item = replaceTarget.value
  if (!item) return []
  const logs: SlotOperationLog[] = []
  if (item.batch_created_at) logs.push({
    key: `created-${item.id}`,
    createdAt: item.batch_created_at,
    action: '策划结果生成',
    actor: item.plan_type === 'manual' ? '人工策划' : 'AI 自动策划',
    detail: `批次 ${item.batch_code || '—'} · ${slotLabel(item.slot_type, item.plan_type)}`,
  })
  for (const record of adjustmentHistory.value) logs.push({
    key: `adjustment-${record.id}`,
    createdAt: record.created_at,
    action: record.adjustment_source || '选题调整',
    actor: record.created_by || '—',
    detail: `${record.old_topic_title || record.old_topic_id} → ${record.new_topic_title || record.new_topic_id}${record.reason ? ` · ${record.reason}` : ''}`,
  })
  return logs.sort((a, b) => b.createdAt.localeCompare(a.createdAt))
})
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
  (!appliedReplacementFilters.value.topicId.trim() || topic.topic_id === appliedReplacementFilters.value.topicId.trim()) &&
  (!appliedReplacementFilters.value.query.trim() || topic.topic_title.toLocaleLowerCase().includes(appliedReplacementFilters.value.query.trim().toLocaleLowerCase())) &&
  (!appliedReplacementFilters.value.marketing || String(topic.is_marketing) === appliedReplacementFilters.value.marketing) &&
  (!appliedReplacementFilters.value.contentType || topic.content_type === appliedReplacementFilters.value.contentType) &&
  (!appliedReplacementFilters.value.product || topic.related_product === appliedReplacementFilters.value.product) &&
  (!appliedReplacementFilters.value.activity || topic.related_activity === appliedReplacementFilters.value.activity) &&
  (!appliedReplacementFilters.value.hotspot || topic.related_hotspot === appliedReplacementFilters.value.hotspot),
))
function applyReplacementFilters() {
  flushSearch()
  appliedReplacementFilters.value = { topicId: replacementTopicIdFilter.value, query: replacementQuery.value, marketing: replacementMarketingFilter.value, contentType: replacementContentType.value, product: replacementProduct.value, activity: replacementActivity.value, hotspot: replacementHotspot.value }
}
function replacementTopicType(topic: TopicOption) {
  return topic.topic_type || (topic.is_marketing ? '\u8425\u9500' : '\u666e\u901a')
}
async function openReplacement(item: AccountPlanRecord) {
  if (!canReplacePlanTopic(item)) return
  const request = ++planDetailRequest
  replacementReturnsToDetails = drawerMode.value === 'view' && replaceTarget.value?.id === item.id
  replacementReturnScrollTop = planDrawerBody.value?.scrollTop ?? 0
  error.value = ''
  drawerMode.value = 'replace'
  replaceTarget.value = item
  replacementFiltersExpanded.value = false
  appliedReplacementFilters.value = { topicId: '', query: '', marketing: '', contentType: '', product: '', activity: '', hotspot: '' }
  replacementQuery.value = ''
  replacementTopicIdFilter.value = ''
  replacementMarketingFilter.value = ''
  replacementContentType.value = ''
  replacementProduct.value = ''
  replacementActivity.value = ''
  replacementHotspot.value = ''
  replacementTopicId.value = ''
  replacementReason.value = ''
  replacementTopics.value = []
  adjustmentHistory.value = []
  try {
    const [topics, history, taxonomy] = await Promise.all([api.replacementCandidates(item.id), api.adjustments(item.id), api.tagTaxonomy()])
    if (request !== planDetailRequest) return
    taxonomyItems.value = taxonomy.items
    replacementTopics.value = topics
    adjustmentHistory.value = history
  } catch (exc) { if (request === planDetailRequest) error.value = exc instanceof Error ? exc.message : '读取替换信息失败' }
}
async function showCurrentTopicDetails(item: AccountPlanRecord) {
  detailTopic.value = topicCatalog.value.find(topic => topic.topic_id === item.topic_id) ?? { topic_id: item.topic_id, topic_title: item.topic_title, outline: item.outline, content_type: item.content_type, category: '', is_marketing: item.topic_type === '营销', status: '可用', topic_type: item.topic_type === '营销' ? '营销' : item.topic_type === '热点' ? '热点' : '普通' }
  try { taxonomyItems.value = (await api.tagTaxonomy()).items } catch { /* Existing topic paths remain readable. */ }
}
async function openPlanDetails(item: AccountPlanRecord, known?: { topic?: TopicOption; adjustments?: AdjustmentRecord[] }) {
  const request = ++planDetailRequest
  drawerMode.value = 'view'
  replaceTarget.value = item
  adjustmentHistory.value = known?.adjustments ?? []
  planOperationsError.value = ''
  planOperationsLoading.value = !known?.adjustments
  const catalogTopic = known?.topic ?? topicCatalog.value.find(topic => topic.topic_id === item.topic_id) ?? null
  planTopicDetail.value = catalogTopic ?? {
    topic_id: item.topic_id,
    topic_title: item.topic_title,
    outline: item.outline,
    content_type: item.content_type,
    category: '',
    is_marketing: item.topic_type === '营销' || item.topic_type === 'marketing',
    status: '可用',
    topic_type: topicTypeLabel(item) === '热点' ? '热点' : topicTypeLabel(item) === '营销' ? '营销' : '普通',
  }
  planDetailLoading.value = !catalogTopic && Boolean(item.topic_id)
  const [operationsResult, topicResult] = await Promise.allSettled([
    known?.adjustments ? Promise.resolve(known.adjustments) : api.adjustments(item.id),
    !catalogTopic && item.topic_id ? api.topicDetail(item.topic_id, topicTypeLabel(item)) : Promise.resolve(catalogTopic),
  ])
  if (request !== planDetailRequest) return
  if (operationsResult.status === 'fulfilled') adjustmentHistory.value = operationsResult.value
  else planOperationsError.value = operationsResult.reason instanceof Error ? operationsResult.reason.message : '操作记录暂不可用'
  if (topicResult.status === 'fulfilled' && topicResult.value) planTopicDetail.value = topicResult.value
  else if (topicResult.status === 'rejected') planDetailLoading.value = false
  planDetailLoading.value = false
  planOperationsLoading.value = false
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
function closeReplacement() {
  planDetailRequest++
  replaceTarget.value = null
  planDetailLoading.value = false
  planOperationsLoading.value = false
  if (props.detailOnly) emit('closePlan')
}
async function confirmReplacement() {
  if (replaceBusy.value || !replaceTarget.value || !canReplacePlanTopic(replaceTarget.value) || !replacementTopicId.value || replaceTarget.value.result_version == null) return
  const request = planDetailRequest
  const returnToDetails = replacementReturnsToDetails
  const returnScrollTop = replacementReturnScrollTop
  const topic = replacementTopics.value.find(topic => topic.topic_id === replacementTopicId.value)
  replaceBusy.value = true
  error.value = ''
  try {
    const result = await api.replaceTopic(replaceTarget.value.id, replacementTopicId.value, replaceTarget.value.result_version, replacementReason.value.trim())
    const update = (rows: AccountPlanRecord[]) => rows.map(row => row.id === result.item.id ? result.item : row)
    cycleItems.value = update(cycleItems.value)
    if (selectedAccount.value) selectedAccount.value = { ...selectedAccount.value, items: update(selectedAccount.value.items) }
    emit('planUpdated', result.item)
    if (request !== planDetailRequest || replaceTarget.value?.id !== result.item.id || drawerMode.value !== 'replace') return
    const adjustments = [result.adjustment, ...adjustmentHistory.value.filter(row => row.id !== result.adjustment.id)]
    replacementTopicId.value = ''
    if (returnToDetails) {
      void openPlanDetails(result.item, { topic, adjustments })
      await nextTick()
      if (planDrawerBody.value) planDrawerBody.value.scrollTop = returnScrollTop
    } else closeReplacement()
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '替换失败，当前结果未改变' }
  finally { replaceBusy.value = false }
}
function openAccountDetail(group: AccountGroup) {
  accountReturnPane.value = 'detail'
  pane.value = 'account'
  void loadAccountHistory(group)
}
function openPlanningAccount(account: PlanningAccountSummary) {
  if (props.externalNavigation) {
    emit('viewPlans', account)
    return
  }
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
async function loadBatch(batchId: number) {
  if (!store.databaseReady) return
  busy.value = true
  error.value = ''
  try {
    const batch = await api.batch(batchId)
    selectedBatch.value = batch
    expandedBatchAccountIds.value = new Set()
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
    appliedBatchDetailFilters.value = { keyword: '', planType: batch.plan_type, contentType: 'all' }
    pane.value = 'detail'
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '\u8bfb\u53d6\u6279\u6b21\u5931\u8d25' }
  finally { busy.value = false }
}
function toggleBatchAccount(accountId: string) {
  const expanded = new Set(expandedBatchAccountIds.value)
  if (expanded.has(accountId)) expanded.delete(accountId)
  else expanded.add(accountId)
  expandedBatchAccountIds.value = expanded
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


watch(() => [route.query.batch, batchSummaries.value.length] as const, async ([id, count]) => {
  if (props.detailOnly) return
  if (!count || typeof id !== 'string' || !/^\d+$/.test(id)) return
  await loadBatch(Number(id))
}, { immediate: true })
watch(() => store.databaseReady, ready => { if (ready && !props.detailOnly) void refresh() }, { immediate: true })
watch(() => props.profiles, profiles => {
  if (props.detailOnly) accountCatalog.value = profiles
}, { immediate: true })
watch(() => props.plan, item => {
  if (!props.detailOnly || !item) return
  void openPlanDetails(item)
  void api.tagTaxonomy().then(taxonomy => { taxonomyItems.value = taxonomy.items }).catch(() => {
    // Historical topic labels remain readable when the current taxonomy is unavailable.
  })
}, { immediate: true })
onBeforeUnmount(() => { planDetailRequest++ })
</script>

<template>
  <template v-if="!detailOnly">
  <div v-if="visibleError" class="banner error-banner" role="alert">{{ visibleError }}</div>
  <div v-if="pane !== 'detail' && !selectedAccount" class="result-tabs" role="group" aria-label="策划结果查看方式"><button type="button" :class="{ active: pane === 'account' }" :aria-pressed="pane === 'account'" @click="pane = 'account'">账号列表</button><button type="button" :class="{ active: pane === 'period' }" :aria-pressed="pane === 'period'" @click="pane = 'period'">时间列表</button></div>
  <section v-if="listLoading" class="card"><LoadingSkeleton /></section>
  <section v-if="pane === 'period' && !listLoading" class="card">
    <div class="card-body batch-dimension-filters">
      <button class="filter-collapse-toggle" type="button" aria-controls="batch-dimension-filter-fields" :aria-expanded="batchFiltersExpanded" @click="batchFiltersExpanded = !batchFiltersExpanded"><span>&#x7B5B;&#x9009;&#x6761;&#x4EF6;</span><svg :class="{ expanded: batchFiltersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg></button>
      <div id="batch-dimension-filter-fields" v-show="batchFiltersExpanded" class="batch-filter-fields">
        <div class="batch-filter-row query-filter-grid" data-query-filters="standard">
          <select v-model="batchYear"><option value="all">&#x5168;&#x90E8;&#x5E74;&#x4EFD;</option><option v-for="value in batchYearOptions" :key="value" :value="value">{{ value }} &#x5E74;</option></select>
          <select v-model="batchMonth"><option value="all">&#x5168;&#x90E8;&#x6708;&#x4EFD;</option><option v-for="value in batchMonthOptions" :key="value" :value="value">{{ Number(value) }} &#x6708;</option></select>
          <div class="query-filter-tail">
                <select v-model="batchWeek"><option value="all">&#x5168;&#x90E8;&#x5468;&#x6B21;</option><option v-for="value in batchWeekOptions" :key="value" :value="String(value)">&#x7B2C;{{ value }}&#x5468;</option></select>
                <div class="query-filter-actions"><button class="btn primary" type="button" @click="applyBatchFilters">&#x67E5;&#x8BE2;</button></div>
              </div>
        </div>
      </div>
    </div>
    <div class="table-wrap"><table><thead><tr><th>&#x6279;&#x6B21;</th><th>&#x7B56;&#x5212;&#x65B9;&#x5F0F;</th><th>&#x6279;&#x6B21;&#x5468;&#x671F;</th><th>&#x8D26;&#x53F7;&#x6570;</th><th>&#x5B8C;&#x6210;&#x6570;</th><th>&#x5931;&#x8D25;&#x6570;</th><th>&#x9009;&#x9898;&#x6570;</th><th>&#x7B56;&#x5212;&#x72B6;&#x6001;</th><th title="完成内容生产的账号数 / 总账号数">内容进度</th><th>&#x66F4;&#x65B0;&#x65F6;&#x95F4;</th><th>&#x64CD;&#x4F5C;</th></tr></thead><tbody>
      <tr v-for="batch in pagedBatches" :key="batch.id"><td><div class="account-name-cell"><b>{{ batch.task_name || '\u2014' }}</b><small>ID {{ batch.batch_code }}</small></div></td><td>{{ batch.plan_type === 'manual' ? '\u624b\u52a8\u7b56\u5212' : '\u81ea\u52a8\u7b56\u5212' }}</td><td>{{ batch.cycle_start }} &#x81F3; {{ batch.cycle_end }}</td><td>{{ batch.account_count }}</td><td class="batch-count" :class="{ completed: batch.completed_count > 0 }">{{ batch.completed_count }}</td><td class="batch-count" :class="{ failed: batch.failed_count > 0 }">{{ batch.failed_count }}</td><td>{{ batch.topic_count }}</td><td><span :class="['tag', statusTagClass(batch.planning_status)]">{{ batch.planning_status || batch.status }}</span></td><td><ContentProgress display="status" :completed="batch.content_completed_account_count" :total="batch.account_count" /></td><td>{{ formatDateTime(batch.updated_at || batch.created_at) }}</td><td><button class="text-btn" type="button" @click="loadBatch(batch.id)">&#x67E5;&#x770B;&#x8BE6;&#x60C5;</button></td></tr>
      <tr v-if="visibleCycles.length === 0"><td colspan="11"><div class="empty-state"><b>&#x6682;&#x65E0;&#x7B56;&#x5212;&#x6279;&#x6B21;</b></div></td></tr>
    </tbody></table></div>
    <ListPagination v-model:page="batchListPage" v-model:page-size="batchListPageSize" :total="visibleCycles.length" unit="个批次" class="list-pagination-inset" />
  </section>
  <section v-if="pane === 'detail'" class="card">
    <div class="card-head"><div><h2>策划明细</h2><small v-if="selectedBatch">{{ selectedBatch.batch_code }} &#xB7; {{ selectedBatch.cycle_start }} &#x81F3; {{ selectedBatch.cycle_end }}</small></div><button class="btn" type="button" @click="pane = 'period'">返回时间列表</button></div>
    <LoadingSkeleton v-if="busy" :rows="8" />
    <template v-else-if="selectedBatch">
    <section class="batch-dashboard" aria-label="批次看板">
      <div class="batch-dashboard-item"><small>账号数</small><strong>{{ batchDashboard.accountCount }}</strong></div>
      <div class="batch-dashboard-item"><small>总策划条数</small><strong>{{ batchDashboard.totalPlanningCount }}</strong></div>
      <div class="batch-dashboard-item"><small>热点策划条数</small><strong>{{ batchDashboard.hotspotCount }}</strong></div>
      <div class="batch-dashboard-item"><small>营销策划条数</small><strong>{{ batchDashboard.marketingCount }}</strong></div>
      <div class="batch-dashboard-item"><small>普通策划条数</small><strong>{{ batchDashboard.regularCount }}</strong></div>
      <div class="batch-dashboard-item pending"><small>热点待填充条数</small><strong>{{ batchDashboard.hotspotPendingCount }}</strong></div>
    </section>
    <div class="card-body filter-collapse-row"><button class="filter-collapse-toggle" type="button" aria-controls="batch-detail-filter-fields" :aria-expanded="batchDetailFiltersExpanded" @click="batchDetailFiltersExpanded = !batchDetailFiltersExpanded"><span>&#x7B5B;&#x9009;&#x6761;&#x4EF6;</span><svg :class="{ expanded: batchDetailFiltersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg></button></div>
    <div id="batch-detail-filter-fields" v-show="batchDetailFiltersExpanded" class="card-body detail-filter-fields query-filter-grid" data-query-filters="standard">
      <label><span>&#x8D26;&#x53F7; ID &#x6216;&#x6635;&#x79F0;</span><input v-model="cycleAccountKeyword" type="search" placeholder="&#x8F93;&#x5165;&#x8D26;&#x53F7; ID &#x6216;&#x6635;&#x79F0;" /></label>
      <label><span>&#x7B56;&#x5212;&#x65B9;&#x5F0F;</span><select v-model="cycleDetailPlanType"><option value="all">&#x5168;&#x90E8;</option><option value="auto">&#x81EA;&#x52A8;&#x7B56;&#x5212;</option><option value="manual">&#x624B;&#x52A8;&#x7B56;&#x5212;</option></select></label>
      <div class="query-filter-tail">
                <label><span>&#x5185;&#x5BB9;&#x7C7B;&#x578B;</span><select v-model="cycleContentType"><option value="all">&#x5168;&#x90E8;&#x5185;&#x5BB9;&#x7C7B;&#x578B;</option><option v-for="value in dimensionContentTypes" :key="value" :value="value">{{ value }}</option></select></label>
                <div class="result-filter-action-row query-filter-actions"><button class="btn primary" type="button" @click="applyBatchDetailFilters">&#x67E5;&#x8BE2;</button></div>
              </div>
    </div>
    <div v-if="groupedCycleItems.length" class="batch-account-list planning-account-groups">
      <article v-for="group in pagedGroupedCycleItems" :key="group.account_id" class="batch-account-card planning-account-group">
        <div class="batch-account-head planning-account-group-head">
          <div><div class="batch-account-name"><button class="account-detail-link" type="button" @click="openAccountDetail(group)">{{ group.account_name }}</button><span class="tag gray">{{ group.account_id }}</span><span v-if="group.lifecycle_stage && group.lifecycle_stage !== ''" class="tag purple">{{ group.lifecycle_stage }}</span></div></div>
          <div class="batch-account-head-actions"><span class="tag blue">{{ group.items.length }} &#x6761;&#x7B56;&#x5212;</span><button class="batch-account-expand" type="button" :aria-expanded="expandedBatchAccountIds.has(group.account_id)" :aria-label="`${expandedBatchAccountIds.has(group.account_id) ? '收起' : '展开'}${group.account_name}的策划详情`" @click="toggleBatchAccount(group.account_id)"><svg :class="{ expanded: expandedBatchAccountIds.has(group.account_id) }" width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg></button></div>
        </div>
        <div v-if="expandedBatchAccountIds.has(group.account_id)" class="account-week-carousel"><button class="account-week-scroll-control previous" type="button" aria-label="&#x5411;&#x5DE6;&#x6ED1;&#x52A8;&#x5468;&#x5386;" @click="scrollAccountWeek($event, -1)"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m12 4-6 6 6 6" /></svg></button><div class="account-week-scroll"><div class="account-week-calendar">
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
      <div class="card-head"><div><h2>策划明细</h2><small>{{ selectedAccount.account_name }} · {{ selectedAccount.account_id }}</small></div><button class="btn" type="button" @click="returnFromAccountDetail">{{ accountReturnPane === 'detail' ? '返回策划明细' : '返回账号列表' }}</button></div>
      <div class="card-body filter-collapse-row"><button class="filter-collapse-toggle" type="button" aria-controls="account-detail-filter-fields" :aria-expanded="accountDetailFiltersExpanded" @click="accountDetailFiltersExpanded = !accountDetailFiltersExpanded"><span>&#x7B5B;&#x9009;&#x6761;&#x4EF6;</span><svg :class="{ expanded: accountDetailFiltersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg></button></div>
      <div id="account-detail-filter-fields" v-show="accountDetailFiltersExpanded" class="card-body detail-filter-fields query-filter-grid" data-query-filters="compact">
        <label><span>&#x6279;&#x6B21;</span><select v-model="accountHistoryBatchId" @change="changeAccountDetailBatch(accountHistoryBatchId)"><option value="all">&#x5168;&#x90E8;&#x6279;&#x6B21;</option><option v-for="batch in accountDetailBatchOptions" :key="batch.id" :value="String(batch.id)">{{ batch.label }}</option></select></label>
        <div class="query-filter-tail">
                <label><span>&#x7B56;&#x5212;&#x65B9;&#x5F0F;</span><select v-model="accountHistoryPlanType"><option value="all">&#x5168;&#x90E8;</option><option value="auto">&#x81EA;&#x52A8;&#x7B56;&#x5212;</option><option value="manual">&#x624B;&#x52A8;&#x7B56;&#x5212;</option></select></label>
                <div class="result-filter-action-row query-filter-actions"><button class="btn primary" type="button" @click="applyAccountDetailFilters">&#x67E5;&#x8BE2;</button></div>
              </div>
      </div>
      <LoadingSkeleton v-if="busy" :rows="8" />
      <div v-else-if="accountHistoryGroups.length" class="batch-account-list account-history-batches">
        <article v-for="history in pagedAccountHistoryGroups" :key="history.batch_id" class="batch-account-card account-history-batch">
          <div class="batch-account-head account-history-batch-head">
            <div class="account-history-batch-title"><b>{{ history.task_name }}</b><small>{{ history.batch_code }} ? {{ history.cycle_start }} ? {{ history.cycle_end }}</small></div>
            <div class="account-history-batch-counts"><span class="tag gray">{{ history.plan_type === 'manual' ? '人工策划' : '自动策划' }}</span><span class="tag blue">{{ history.items.length }} &#x6761;&#x7B56;&#x5212;</span></div>
          </div>
          <div class="account-history-record-list">
            <article v-for="record in history.items" :key="record.id" class="account-history-record">
              <div class="account-history-record-date"><b>{{ record.publish_date }}</b><small>{{ weekdayLabel(record.publish_date) }}</small></div>
              <div class="account-history-record-content">
                <div class="account-history-record-heading"><h3>{{ record.topic_title || (record.topic_id ? '暂无选题标题' : '待定题') }}</h3><span :class="['tag', statusTagClass(productionStatusLabel(record))]">{{ productionStatusLabel(record) }}</span></div>
                <p>{{ record.outline || '\u6682\u65e0\u9009\u9898\u5927\u7eb2' }}</p>
                <div class="account-history-record-meta"><span>{{ record.content_type || '—' }}</span><span>{{ topicTypeLabel(record) }}</span><span>{{ plannedSlotLabel(record) }}&#x69FD;&#x4F4D;</span></div>
              </div>
            </article>
          </div>
        </article>
        <ListPagination v-model:page="accountHistoryPage" v-model:page-size="accountHistoryPageSize" :total="accountHistoryGroups.length" unit="&#x4E2A;&#x6279;&#x6B21;" />
      </div>
      <div v-else class="empty-state"><b>当前筛选范围内暂无策划数据</b></div>
    </template>
    <template v-else>
      <div class="card-body filter-collapse-row"><button class="filter-collapse-toggle" type="button" aria-controls="account-dimension-filter-fields" :aria-expanded="accountFiltersExpanded" @click="accountFiltersExpanded = !accountFiltersExpanded"><span>&#x7B5B;&#x9009;&#x6761;&#x4EF6;</span><svg :class="{ expanded: accountFiltersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg></button></div>
      <div id="account-dimension-filter-fields" v-show="accountFiltersExpanded" class="card-body account-history-toolbar query-filter-grid" data-query-filters="standard">
        <label><span>&#x751F;&#x547D;&#x5468;&#x671F;</span><select v-model="historyLifecycle"><option value="">&#x5168;&#x90E8;</option><option v-for="item in historyLifecycleOptions" :key="item" :value="item">{{ item }}</option></select></label>
        <label><span>&#x7C89;&#x4E1D;&#x91CF;</span><div class="account-history-follower-range"><input v-model.number="historyFollowersMin" type="number" min="0" placeholder="&#x8D77;&#x59CB;&#x7C89;&#x4E1D;&#x91CF;" /><i>&#x81F3;</i><input v-model.number="historyFollowersMax" type="number" min="0" placeholder="&#x622A;&#x6B62;&#x7C89;&#x4E1D;&#x91CF;" /></div></label>
        <label><span>&#x8D26;&#x53F7;&#x7C7B;&#x578B;</span><select v-model="historyAccountType"><option value="">&#x5168;&#x90E8;</option><option value="&#x8BA4;&#x8BC1;">&#x8BA4;&#x8BC1;</option><option value="&#x975E;&#x8BA4;&#x8BC1;">&#x975E;&#x8BA4;&#x8BC1;</option></select></label>
        <label><span>&#x5C5E;&#x4E3B;&#x7EC4;&#x7EC7;</span><select v-model="historyOrganization"><option value="">&#x5168;&#x90E8;</option><option v-for="item in historyOrganizationOptions" :key="item" :value="item">{{ item }}</option></select></label>
        <label><span>&#x5E73;&#x53F0;</span><select v-model="historyPlatform"><option value="">&#x5168;&#x90E8;</option><option v-for="item in historyPlatformOptions" :key="item" :value="item">{{ item }}</option></select></label>

        <label><span>&#x8D26;&#x53F7; ID &#x6216;&#x6635;&#x79F0;</span><input v-model="historyAccountKeyword" type="search" placeholder="&#x8F93;&#x5165;&#x8D26;&#x53F7; ID &#x6216;&#x6635;&#x79F0;" /></label>
        <div class="query-filter-tail">
                <label><span>&#x5C5E;&#x4E3B; UM &#x53F7;</span><input v-model="historyUmNo" type="search" placeholder="&#x8F93;&#x5165;&#x5C5E;&#x4E3B; UM &#x53F7;" /></label>
                <div class="result-filter-action-row query-filter-actions"><button class="btn primary" type="button" @click="applyAccountFilters">&#x67E5;&#x8BE2;</button></div>
              </div>
      </div>

      <div ref="accountTableScroll" class="table-wrap account-dimension-table-scroll" tabindex="0" role="region" aria-label="&#x8D26;&#x53F7;&#x5217;&#x8868;"><table><thead><tr><th>&#x8D26;&#x53F7;</th><th>&#x5C5E;&#x4E3B; UM &#x53F7;</th><th>&#x5C5E;&#x4E3B;&#x7EC4;&#x7EC7;</th><th>&#x8D26;&#x53F7;&#x7C7B;&#x578B;</th><th>&#x5E73;&#x53F0;</th><th>&#x751F;&#x547D;&#x5468;&#x671F;</th><th>&#x7C89;&#x4E1D;&#x91CF;</th><th>&#x8D26;&#x53F7;&#x72B6;&#x6001;</th><th>&#x7B56;&#x5212;&#x7ED3;&#x679C;</th></tr></thead><tbody>
        <tr v-for="account in pagedPlanningAccounts" :key="account.account_id"><td><div class="account-name-cell"><b>{{ account.account_name }}</b><small>{{ account.account_id }}</small></div></td><td>{{ getAccountProfile(account.account_id)?.um_no || '\u2014' }}</td><td>{{ getAccountProfile(account.account_id)?.organization || account.account_owner || '\u2014' }}</td><td><AccountTypeBadge :type="accountTypeLabel(account.account_id)" /></td><td>{{ getAccountProfile(account.account_id)?.platform || '\u2014' }}</td><td>{{ getAccountProfile(account.account_id)?.lifecycle_stage || '\u2014' }}</td><td>{{ followersLabel(account.account_id) }}</td><td><span :class="['tag', getAccountProfile(account.account_id)?.status === '\u542f\u7528' ? 'green' : 'gray']">{{ getAccountProfile(account.account_id)?.status || '\u2014' }}</span></td><td><button class="text-btn" type="button" @click="openPlanningAccount(account)">查看策划</button></td></tr>
        <tr v-if="visiblePlanningAccounts.length === 0"><td colspan="9"><div class="empty-state">{{ planningAccounts.length ? '\u6ca1\u6709\u5339\u914d\u7684\u8d26\u53f7' : '\u6682\u65e0\u53c2\u4e0e\u7b56\u5212\u7684\u8d26\u53f7' }}</div></td></tr>
      </tbody></table></div>
      <ListPagination v-model:page="accountListPage" v-model:page-size="accountListPageSize" :total="visiblePlanningAccounts.length" unit="个账号" class="list-pagination-inset" />
    </template>
  </section>
  </template>
  <div v-if="replaceTarget" class="drawer-mask" @click.self="closeReplacement">
    <aside class="drawer" role="dialog" aria-modal="true" :aria-label="drawerMode === 'view' ? String.fromCharCode(35745,21010,35814,24773) : drawerMode === 'replace' ? String.fromCharCode(26367,25442,36873,39064) : String.fromCharCode(26597,30475,35843,25972,35760,24405)">
      <div class="drawer-head"><div><small>{{ drawerMode === 'view' ? String.fromCharCode(35745,21010,35814,24773) : drawerMode === 'replace' ? String.fromCharCode(26367,25442,36873,39064) : String.fromCharCode(26597,30475,35843,25972,35760,24405) }}</small><h2>{{ replaceTarget.account_name }}</h2></div><button class="icon-btn" type="button" aria-label="&#20851;&#38381;" @click="closeReplacement">&times;</button></div>
      <div ref="planDrawerBody" class="drawer-body">
        <div v-if="error && drawerMode === 'replace'" class="banner error-banner" role="alert">{{ error }}</div>
        <template v-if="drawerMode === 'view'">
          <section class="slot-detail-section"><h3>策划信息</h3><div class="slot-detail-grid"><div><small>投放日期</small><b>{{ replaceTarget.publish_date }} · {{ weekdayLabel(replaceTarget.publish_date) }}</b></div><div><small>批次周期</small><b>{{ replaceTarget.cycle_start }} 至 {{ replaceTarget.cycle_end }}</b></div><div><small>批次编号</small><b>{{ replaceTarget.batch_code || '—' }}</b></div><div><small>策划方式</small><b>{{ replaceTarget.plan_type === 'manual' ? '人工策划' : 'AI 自动策划' }}</b></div><div><small>经营阶段</small><b>{{ replaceTarget.lifecycle_stage || '—' }}</b></div><div><small>经营作用</small><b>{{ replaceTarget.content_role || '—' }}</b></div><div><small>内容状态</small><b>{{ productionStatusLabel(replaceTarget) }}</b></div></div></section>
          <section class="slot-detail-section"><h3>账号信息</h3><div class="slot-detail-grid"><div><small>用户 UM 号</small><b>{{ getAccountProfile(replaceTarget.account_id)?.um_no || '—' }}</b></div><div><small>账号昵称</small><b>{{ replaceTarget.account_name || '—' }}</b></div><div><small>账号 ID</small><b>{{ replaceTarget.account_id || '—' }}</b></div><div><small>账号类型</small><b>{{ accountTypeLabel(replaceTarget.account_id) }}</b></div><div><small>所属分行</small><b>{{ getAccountProfile(replaceTarget.account_id)?.organization || '—' }}</b></div><div><small>人设标签</small><b>{{ getAccountProfile(replaceTarget.account_id)?.persona || '—' }}</b></div></div></section>
          <section class="slot-detail-section"><div class="slot-detail-section-head"><h3>选题信息</h3><button v-if="canReplacePlanTopic(replaceTarget)" class="btn primary" type="button" @click="openReplacement(replaceTarget)">&#x66FF;&#x6362;&#x9009;&#x9898;</button></div><div v-if="planDetailLoading" class="slot-detail-loading">正在读取选题信息…</div><template v-else-if="planTopicDetail"><div class="slot-detail-grid"><div><small>内容类型</small><b>{{ planTopicDetail.content_type || replaceTarget.content_type || '—' }}</b></div><div><small>选题 ID</small><b>{{ planTopicDetail.topic_id || '—' }}</b></div><div class="slot-detail-wide"><small>选题标题</small><b>{{ planTopicDetail.topic_title || replaceTarget.topic_title || '—' }}</b></div><div class="slot-detail-wide"><small>选题大纲</small><b class="slot-detail-outline">{{ planTopicDetail.outline || replaceTarget.outline || '—' }}</b></div><div class="slot-detail-wide"><small>选题有效期</small><b>{{ planTopicDetail.valid_from?.slice(0, 10) || '不限' }} 至 {{ planTopicDetail.valid_to?.slice(0, 10) || '不限' }}</b></div></div><div class="slot-topic-label-groups"><div v-for="group in planTopicTagGroups" :key="group.name"><small>{{ group.name }}</small><div v-if="group.values.length" class="slot-topic-labels"><span v-for="label in group.values" :key="label">{{ label }}</span></div><b v-else class="slot-topic-label-empty">未识别</b></div></div></template><div v-else class="empty-state">暂无选题信息</div></section>
          <section class="slot-detail-section"><h3>操作记录</h3><div v-if="planOperationsLoading" class="slot-detail-loading">正在读取操作记录…</div><div v-else-if="planOperationsError" class="detail-note" role="alert">{{ planOperationsError }}</div><div v-else-if="planOperationLogs.length" class="slot-operation-list"><article v-for="log in planOperationLogs" :key="log.key" class="slot-operation-item"><span class="slot-operation-dot" aria-hidden="true"/><div class="slot-operation-content"><div><b>{{ log.action }}</b><time>{{ formatDateTime(log.createdAt) }}</time></div><p>{{ log.detail }}</p><small>操作方：{{ log.actor }}</small></div></article></div><div v-else class="empty-state">暂无操作记录</div></section>
        </template>
        <template v-else>
        <div class="detail-note"><b>&#x5F53;&#x524D;&#x9009;&#x9898;:</b>{{ replaceTarget.topic_title }}<br /><b>&#x6295;&#x653E;&#x65E5;&#x671F;:</b>{{ replaceTarget.publish_date }}<br /><b>&#x7C7B;&#x578B;:</b>{{ slotLabel(replaceTarget.slot_type, replaceTarget.plan_type) }}<br /><b>&#x72B6;&#x6001;:</b>{{ replaceTarget.publish_status }}</div>
        <template v-if="drawerMode === 'replace' && canReplacePlanTopic(replaceTarget)">
          <h3>选择新选题</h3>
          <div class="replacement-filter-collapse-row"><button class="filter-collapse-toggle" type="button" aria-controls="replacement-topic-filters" :aria-expanded="replacementFiltersExpanded" @click="replacementFiltersExpanded = !replacementFiltersExpanded"><span>筛选条件</span><svg :class="{ expanded: replacementFiltersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg></button></div>
          <div id="replacement-topic-filters" v-show="replacementFiltersExpanded" class="replacement-topic-filters query-filter-grid" data-query-filters="narrow">
            <label class="field"><span class="field-label-with-tip">选题 ID <span class="field-help-tip" tabindex="0" title="输入完整选题 ID，进行精确匹配">?</span></span><input v-model="replacementTopicIdFilter" type="text" inputmode="text" autocomplete="off" placeholder="输入完整选题 ID" /></label>
            <label class="field"><span class="field-label-with-tip">选题标题 <span class="field-help-tip" tabindex="0" title="输入标题关键词，进行模糊搜索">?</span></span><input v-model="replacementQuery" type="search" placeholder="输入选题标题关键词" /></label>
            <label class="field"><span>选题类型</span><select v-model="replacementMarketingFilter"><option value="">全部</option><option value="true">营销</option><option value="false">非营销</option></select></label>
            <label class="field"><span>内容类型</span><select v-model="replacementContentType"><option value="">全部</option><option v-for="value in replacementContentTypes" :key="value" :value="value">{{ value }}</option></select></label>
            <label class="field"><span>关联产品</span><select v-model="replacementProduct"><option value="">全部</option><option v-for="value in replacementProducts" :key="value" :value="value">{{ value }}</option></select></label>
            <label class="field"><span>关联活动</span><select v-model="replacementActivity"><option value="">全部</option><option v-for="value in replacementActivities" :key="value" :value="value">{{ value }}</option></select></label>
            <div class="query-filter-tail">
                <label class="field"><span>关联属地热点</span><select v-model="replacementHotspot"><option value="">全部</option><option v-for="value in replacementHotspots" :key="value" :value="value">{{ value }}</option></select></label>
                <div class="replacement-filter-actions query-filter-actions"><button class="text-btn replacement-filter-clear" type="button" @click="replacementTopicIdFilter = ''; replacementQuery = ''; replacementMarketingFilter = ''; replacementContentType = ''; replacementProduct = ''; replacementActivity = ''; replacementHotspot = ''">清空筛选</button><button class="btn primary" type="button" @click="applyReplacementFilters">&#x67E5;&#x8BE2;</button></div>
              </div>
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
        <div v-if="drawerMode === 'replace' && canReplacePlanTopic(replaceTarget)" class="footer-actions"><button class="btn primary" type="button" :disabled="replaceBusy || !replacementTopicId" @click="confirmReplacement">{{ replaceBusy ? '\u4fdd\u5b58\u4e2d\u2026' : '\u786e\u8ba4\u66ff\u6362' }}</button></div>
      </div>
    </aside>
  </div>
  <TopicDetailDrawer v-if="detailTopic" :topic="detailTopic" :items="taxonomyItems" @close="detailTopic = null" />
  <FloatingTableScrollbar v-if="!detailOnly" :target="accountTableScroll" :hidden="!!replaceTarget || !!detailTopic" />
</template>

<style scoped>
.account-dimension-table-scroll{max-width:100%;overflow-x:auto;overflow-y:hidden;overscroll-behavior-x:contain;scrollbar-width:none}
.account-dimension-table-scroll table{width:max-content;min-width:100%}
.account-dimension-table-scroll th,.account-dimension-table-scroll td{min-width:112px;white-space:nowrap}
.account-dimension-table-scroll th:first-child,.account-dimension-table-scroll td:first-child{min-width:220px}
.account-dimension-table-scroll:focus-visible{outline:2px solid var(--primary-300);outline-offset:-2px}
.account-dimension-table-scroll::-webkit-scrollbar{display:none}
.batch-dashboard{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:1px;margin:16px 20px 0;border:1px solid var(--neutral-200);border-radius:12px;overflow:hidden;background:var(--neutral-200)}
.batch-dashboard-item{display:flex;flex-direction:column;gap:8px;min-height:76px;padding:14px 16px;background:var(--surface)}
.batch-dashboard-item small{color:var(--neutral-500);font-size:12px;white-space:nowrap}
.batch-dashboard-item strong{color:var(--neutral-800);font-size:22px;line-height:1;font-variant-numeric:tabular-nums}
.batch-dashboard-item.pending strong{color:var(--warning,#d97706)}
.batch-topic-total{display:flex;align-items:baseline;gap:8px;min-width:150px;padding-right:24px;border-right:1px solid var(--neutral-200)}
.planning-account-group-head{min-height:58px}
.batch-account-expand{display:grid;place-items:center;width:32px;height:32px;padding:0;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface);color:var(--neutral-500);cursor:pointer;transition:background .16s ease,color .16s ease,transform .16s ease}
.batch-account-expand:hover{background:var(--primary-50);color:var(--primary-600)}
.batch-account-expand svg{transition:transform .16s ease}
.batch-account-expand svg.expanded{transform:rotate(180deg)}
.batch-account-expand:focus-visible{outline:2px solid var(--primary-300);outline-offset:2px}
.topic-title-link{padding:0;border:0;background:transparent;color:var(--primary-600);font-size:13px;font-weight:500;text-align:left;line-height:1.6}.topic-title-link:hover{text-decoration:underline}.plan-detail-topic>.text-btn{float:right;font-size:12px}.replacement-topic-filters .field{width:100%}
@media(max-width:980px){.batch-dashboard{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:580px){.batch-dashboard{grid-template-columns:repeat(2,minmax(0,1fr));margin:12px 12px 0}.batch-dashboard-item{min-height:68px;padding:12px}.batch-dashboard-item strong{font-size:20px}}
</style>

<style scoped>
.detail-filter-fields>.btn,.account-history-toolbar>.btn{grid-column:auto;justify-self:end;align-self:end}.result-filter-action-row,.replacement-filter-actions{grid-column:1/-1;display:flex;align-items:end;justify-content:flex-end;gap:8px}.batch-filter-row{grid-template-columns:repeat(3,minmax(130px,1fr)) auto;max-width:900px}.batch-filter-row>.btn{justify-self:end}.slot-detail-section{margin:0 0 14px;padding:16px;border:1px solid var(--neutral-200);border-radius:10px;background:var(--surface)}.slot-detail-section>h3{margin:0 0 12px;color:var(--neutral-800);font-size:14px;line-height:20px}.slot-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px}.slot-detail-grid>div{min-width:0;padding:10px 2px;border-bottom:1px solid var(--neutral-100)}.slot-detail-grid>div:nth-last-child(-n+2){border-bottom:0}.slot-detail-grid small,.slot-topic-label-groups small{display:block;margin-bottom:5px;color:var(--neutral-400);font-size:12px}.slot-detail-grid b{display:block;color:var(--neutral-700);font-size:13px;font-weight:500;line-height:1.55;overflow-wrap:anywhere}.slot-detail-grid .slot-detail-wide{grid-column:1/-1}.slot-detail-grid .slot-detail-outline{white-space:pre-wrap}.slot-topic-label-groups{display:grid;gap:12px;margin-top:12px;padding-top:12px;border-top:1px solid var(--neutral-100)}.slot-topic-label-groups>div{display:grid;grid-template-columns:82px minmax(0,1fr);align-items:start;gap:8px}.slot-topic-label-groups small{margin:3px 0 0}.slot-topic-labels{display:flex;flex-wrap:wrap;gap:6px}.slot-topic-labels span{padding:4px 8px;border-radius:5px;background:var(--primary-50);color:var(--primary-600);font-size:12px;line-height:18px;overflow-wrap:anywhere}.slot-topic-label-empty{padding:4px 0;color:var(--neutral-400);font-size:12px;font-weight:400}.slot-detail-loading{padding:12px 0;color:var(--neutral-400);font-size:13px}.slot-operation-list{position:relative;display:grid;gap:0}.slot-operation-item{position:relative;display:grid;grid-template-columns:14px minmax(0,1fr);gap:10px;padding-bottom:16px}.slot-operation-item:not(:last-child)::before{position:absolute;top:10px;bottom:-2px;left:5px;width:1px;background:var(--neutral-200);content:''}.slot-operation-dot{z-index:1;width:11px;height:11px;margin-top:4px;border:2px solid var(--primary-200);border-radius:50%;background:var(--primary-600)}.slot-operation-content>div{display:flex;justify-content:space-between;align-items:baseline;gap:12px}.slot-operation-content b{color:var(--neutral-700);font-size:13px}.slot-operation-content time,.slot-operation-content small{color:var(--neutral-400);font-size:11px}.slot-operation-content p{margin:5px 0;color:var(--neutral-600);font-size:12px;line-height:1.6;overflow-wrap:anywhere}.slot-operation-content small{display:block}@media(max-width:980px){.batch-filter-row{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:580px){.slot-detail-grid{grid-template-columns:1fr}.slot-detail-grid>div:nth-last-child(-n+2){border-bottom:1px solid var(--neutral-100)}.slot-detail-grid>div:last-child{border-bottom:0}.slot-detail-grid .slot-detail-wide{grid-column:auto}.slot-topic-label-groups>div{grid-template-columns:72px minmax(0,1fr)}.slot-operation-content>div{align-items:flex-start;flex-direction:column;gap:3px}}
</style>


<style scoped>
.slot-detail-section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.slot-detail-section-head h3{margin:0;color:var(--neutral-800);font-size:14px;line-height:20px}.slot-detail-section-head .btn{flex:none}
</style>
