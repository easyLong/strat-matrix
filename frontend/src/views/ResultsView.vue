<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { usePlanningStore } from '../store'
import type { AccountPlanRecord, AdjustmentRecord, BatchSummary, PlanningAccountSummary, PlanningCycleSummary, TopicOption } from '../types'

type AccountGroup = { account_id: string; account_name: string; lifecycle_stage: string; items: AccountPlanRecord[] }

const store = usePlanningStore()
const route = useRoute()
const pane = ref<'period' | 'detail' | 'account'>('period')
const accountListQuery = ref('')
const planningAccounts = ref<PlanningAccountSummary[]>([])
const selectedAccount = ref<AccountGroup | null>(null)
const accountReturnPane = ref<'detail' | 'account'>('detail')
const accountHistoryFrom = ref('')
const accountHistoryTo = ref('')
const accountHistoryAccountId = ref('')
const accountHistoryCycleId = ref('all')
const accountHistoryPage = ref(1)
const accountHistoryPageSize = ref(10)
const batchSummaries = ref<BatchSummary[]>([])
const planningCycleSummaries = ref<PlanningCycleSummary[]>([])
const cycleQuery = ref('')
const cycleItems = ref<AccountPlanRecord[]>([])
const selectedCycle = ref<PlanningCycleSummary | null>(null)
const detailCycleId = ref('')
const cyclePage = ref(1)
const cyclePageSize = ref(10)
const cycleAccountId = ref('all')
const cycleSlotType = ref('all')
const cycleContentType = ref('all')
const cycleRole = ref('all')
const cyclePublishStatus = ref('all')
const error = ref('')
const visibleError = computed(() => error.value
  .split('；')
  .filter(message => !/^\s*(?:404\s*:\s*)?not found\s*$/i.test(message))
  .join('；'))
const busy = ref(false)
const replaceTarget = ref<AccountPlanRecord | null>(null)
const drawerMode = ref<'replace' | 'history'>('replace')
const replacementTopics = ref<TopicOption[]>([])
const replacementQuery = ref('')
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
  return `${value.getUTCFullYear()}年${value.getUTCMonth() + 1}月第${monthWeekOf(date)}周`
}
const visibleCycles = computed(() => planningCycleSummaries.value.filter(cycle =>
  !cycleQuery.value.trim() || `${cycle.cycle_start} ${cycle.cycle_end} ${cyclePeriodLabel(cycle.cycle_start)}`.toLowerCase().includes(cycleQuery.value.trim().toLowerCase()),
))
const visiblePlanningAccounts = computed(() => planningAccounts.value.filter(account =>
  !accountListQuery.value.trim() || `${account.account_name} ${account.account_id}`.toLowerCase().includes(accountListQuery.value.trim().toLowerCase()),
))
const filteredCycleItems = computed(() => cycleItems.value.filter(item =>
  (cycleAccountId.value === 'all' || item.account_id === cycleAccountId.value) &&
  (cycleSlotType.value === 'all' || topicTypeLabel(item) === cycleSlotType.value) &&
  (cycleContentType.value === 'all' || item.content_type === cycleContentType.value) &&
  (cycleRole.value === 'all' || item.content_role === cycleRole.value) &&
  (cyclePublishStatus.value === 'all' || item.publish_status === cyclePublishStatus.value),
))
const selectedCycleStats = computed(() => {
  const items = cycleItems.value
  return {
    accountCount: new Set(items.map(item => item.account_id)).size,
    slotCount: items.length,
    matchedCount: items.filter(item => Boolean(item.topic_id)).length,
    regularCount: items.filter(item => plannedSlotLabel(item) === '普通').length,
    marketingCount: items.filter(item => plannedSlotLabel(item) === '营销').length,
    hotspotCount: items.filter(item => plannedSlotLabel(item) === '热点').length,
  }
})
function groupAccountRecords(items: AccountPlanRecord[]): AccountGroup[] {
  const groups = new Map<string, AccountGroup>()
  for (const item of items) {
    const group = groups.get(item.account_id)
    if (group) group.items.push(item)
    else groups.set(item.account_id, {
      account_id: item.account_id,
      account_name: item.account_name,
      lifecycle_stage: item.lifecycle_stage || '—',
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
const cycleAccountOptions = computed(() => groupAccountRecords(cycleItems.value).map(account => ({
  account_id: account.account_id,
  account_name: account.account_name,
})).sort((a, b) => a.account_name.localeCompare(b.account_name, 'zh-CN')))
const accountHistoryCycleOptions = computed(() => {
  const weeks = new Set((selectedAccount.value?.items ?? []).map(item => cycleWeekStart(item.cycle_start)))
  return [...weeks].sort((a, b) => b.localeCompare(a)).map(value => ({ value, label: cyclePeriodLabel(value) }))
})
const accountHistoryRangeInvalid = computed(() => Boolean(accountHistoryFrom.value && accountHistoryTo.value && accountHistoryFrom.value > accountHistoryTo.value))
const filteredAccountHistory = computed(() => {
  if (!selectedAccount.value || accountHistoryRangeInvalid.value) return []
  return selectedAccount.value.items.filter(item =>
    (!accountHistoryFrom.value || item.publish_date >= accountHistoryFrom.value) &&
    (!accountHistoryTo.value || item.publish_date <= accountHistoryTo.value) &&
    (accountHistoryCycleId.value === 'all' || cycleWeekStart(item.cycle_start) === accountHistoryCycleId.value),
  )
})
const accountHistoryPlanCounts = computed(() => {
  const items = selectedAccount.value?.items ?? []
  return {
    auto: items.filter(item => item.plan_type === 'auto').length,
    manual: items.filter(item => item.plan_type === 'manual').length,
  }
})
watch([cycleAccountId, cycleSlotType, cycleContentType, cycleRole, cyclePublishStatus, cyclePageSize], () => { cyclePage.value = 1 })
watch(cyclePageCount, pageCount => { if (cyclePage.value > pageCount) cyclePage.value = pageCount })
const accountHistoryGroups = computed(() => {
  const groups = new Map<string, {
    batch_id: number | null
    batch_code: string
    batch_created_at: string | null
    plan_type: 'auto' | 'manual'
    cycle_start: string
    cycle_end: string
    items: AccountPlanRecord[]
  }>()
  for (const item of filteredAccountHistory.value) {
    const key = String(item.batch_id ?? item.batch_code)
    const group = groups.get(key)
    if (group) group.items.push(item)
    else groups.set(key, {
      batch_id: item.batch_id ?? null,
      batch_code: item.batch_code,
      batch_created_at: item.batch_created_at,
      plan_type: item.plan_type,
      cycle_start: item.cycle_start,
      cycle_end: item.cycle_end,
      items: [item],
    })
  }
  return [...groups.values()]
    .map(group => ({ ...group, items: group.items.sort((a, b) => a.publish_date.localeCompare(b.publish_date) || a.id - b.id) }))
    .sort((a, b) => (b.batch_created_at ?? '').localeCompare(a.batch_created_at ?? '') || b.cycle_start.localeCompare(a.cycle_start))
})
const accountHistoryPageCount = computed(() => Math.max(1, Math.ceil(accountHistoryGroups.value.length / accountHistoryPageSize.value)))
const pagedAccountHistoryGroups = computed(() => {
  const start = (accountHistoryPage.value - 1) * accountHistoryPageSize.value
  return accountHistoryGroups.value.slice(start, start + accountHistoryPageSize.value)
})
watch([accountHistoryFrom, accountHistoryTo, accountHistoryCycleId, accountHistoryPageSize], () => { accountHistoryPage.value = 1 })
watch(accountHistoryPageCount, pageCount => { if (accountHistoryPage.value > pageCount) accountHistoryPage.value = pageCount })
const cycleContentTypes = computed(() => [...new Set(cycleItems.value.map(item => item.content_type).filter(Boolean))])
const cycleRoles = computed(() => [...new Set(cycleItems.value.map(item => item.content_role).filter((value): value is string => Boolean(value)))])
const cyclePublishStatuses = computed(() => [...new Set(cycleItems.value.map(item => item.publish_status).filter(Boolean))])

function slotLabel(slotType: string, planType: string) {
  if (planType === 'manual') return '手动追加'
  return ({ regular: '普通', marketing_priority: '营销', hotspot: '热点', manual_extra: '手动追加' } as Record<string, string>)[slotType] ?? slotType
}
function plannedSlotLabel(item: AccountPlanRecord) {
  return ({ regular: '普通', marketing_priority: '营销', hotspot: '热点', manual_extra: '手动追加' } as Record<string, string>)[item.slot_type]
    ?? (item.plan_type === 'manual' ? '手动追加' : '普通')
}
function batchStatusLabel(batch: BatchSummary) {
  return batch.plan_type === 'manual' ? '已完成' : batch.status
}
function topicTypeLabel(item: AccountPlanRecord) {
  if (!item.topic_id) return '待确定'
  const type = String(item.topic_type ?? '')
  if (type === '营销' || type === 'marketing' || type === 'marketing_priority') return '营销'
  if (type === '热点' || type === 'hotspot') return '热点'
  if (type === '普通' || type === 'normal' || type === 'regular') return '普通'
  return item.slot_type === 'hotspot' ? '热点' : item.slot_type === 'marketing_priority' ? '营销' : '普通'
}
function weekdayLabel(date: string) {
  return new Intl.DateTimeFormat('zh-CN', { weekday: 'short', timeZone: 'UTC' }).format(new Date(`${date}T00:00:00Z`))
}

const replacementCandidates = computed(() => replacementTopics.value.filter(topic =>
  !replacementQuery.value.trim() ||
  `${topic.topic_title} ${topic.content_type}`.toLowerCase().includes(replacementQuery.value.trim().toLowerCase()),
))
function replacementTopicType(topic: TopicOption) {
  return topic.topic_type || (topic.is_marketing ? '营销' : '普通')
}
async function openReplacement(item: AccountPlanRecord) {
  drawerMode.value = 'replace'
  replaceTarget.value = item
  replacementQuery.value = ''
  replacementTopicId.value = ''
  replacementReason.value = ''
  adjustmentHistory.value = []
  try {
    const [topics, history] = await Promise.all([api.replacementCandidates(item.id), api.adjustments(item.id)])
    replacementTopics.value = topics
    adjustmentHistory.value = history
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '读取替换信息失败' }
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
function changeHistoryAccount(accountId: string) {
  const account = planningAccounts.value.find(item => item.account_id === accountId)
  if (account) void loadAccountHistory(account)
}
function returnFromAccountDetail() {
  selectedAccount.value = null
  pane.value = accountReturnPane.value
}
async function loadBatch(batchId: number) {
  if (!store.databaseReady) return
  error.value = ''
  try {
    const batch = await api.batch(batchId)
    await loadCycle(cycleWeekStart(batch.cycle_start))
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '读取批次周期失败' }
}
async function loadCycle(cycleId: string) {
  if (!store.databaseReady || !cycleId) return
  busy.value = true
  error.value = ''
  try {
    selectedCycle.value = planningCycleSummaries.value.find(cycle => cycle.cycle_id === cycleId) ?? null
    detailCycleId.value = cycleId
    cyclePage.value = 1
    cycleAccountId.value = 'all'
    cycleItems.value = await api.planningCycleItems(cycleId, 5000)
    pane.value = 'detail'
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '读取批次周期失败' }
  finally { busy.value = false }
}
async function chooseDetailCycle() {
  if (detailCycleId.value) await loadCycle(detailCycleId.value)
  else { selectedCycle.value = null; cycleItems.value = [] }
}
async function loadAccountHistory(group: AccountGroup | PlanningAccountSummary) {
  accountHistoryAccountId.value = group.account_id
  selectedAccount.value = { account_id: group.account_id, account_name: group.account_name, lifecycle_stage: 'lifecycle_stage' in group ? group.lifecycle_stage : '—', items: [] }
  accountHistoryFrom.value = ''
  accountHistoryTo.value = ''
  accountHistoryCycleId.value = 'all'
  accountHistoryPage.value = 1
  pane.value = 'account'
  busy.value = true
  error.value = ''
  try {
    const history = await api.accountItems(group.account_id)
    selectedAccount.value = {
      account_id: group.account_id,
      account_name: group.account_name,
      lifecycle_stage: 'lifecycle_stage' in group ? group.lifecycle_stage : '—',
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
    cycles: Set<string>
    slot_count: number
    latest_cycle_start: string
    latest_cycle_updated_at: string | null
  }>()
  for (const items of cycleRows) {
    for (const item of items) {
      const cycleStart = cycleWeekStart(item.cycle_start)
      let group = groups.get(item.account_id)
      if (!group) {
        group = {
          account_id: item.account_id,
          account_name: item.account_name,
          cycles: new Set<string>(),
          slot_count: 0,
          latest_cycle_start: cycleStart,
          latest_cycle_updated_at: item.batch_created_at,
        }
        groups.set(item.account_id, group)
      }
      group.cycles.add(cycleStart)
      group.slot_count += 1
      if (cycleStart > group.latest_cycle_start) group.latest_cycle_start = cycleStart
      if (item.batch_created_at && (!group.latest_cycle_updated_at || item.batch_created_at > group.latest_cycle_updated_at)) {
        group.latest_cycle_updated_at = item.batch_created_at
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
    const [batchesResult, cyclesResult, accountsResult] = await Promise.allSettled([
      api.batches(undefined, 5000),
      api.planningCycles(),
      api.planningAccounts(),
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
    if (failures.length) error.value = failures.join('；')
  }
  catch (exc) { error.value = exc instanceof Error ? exc.message : '刷新失败' }
  finally { busy.value = false }
}


watch(() => [route.query.batch, batchSummaries.value.length] as const, async ([id, count]) => {
  if (!count || typeof id !== 'string' || !/^\d+$/.test(id)) return
  await loadBatch(Number(id))
}, { immediate: true })
watch(() => store.databaseReady, ready => { if (ready) void refresh() }, { immediate: true })
</script>

<template>
  <div class="page-head"><div><h1>策划结果</h1></div><div class="page-actions"><button class="btn" type="button" :disabled="busy || !store.databaseReady" @click="refresh">{{ busy ? '刷新中…' : '刷新结果' }}</button></div></div>
  <div v-if="visibleError" class="banner error-banner" role="alert">{{ visibleError }}</div>
  <div v-if="pane !== 'detail' && !selectedAccount" class="result-tabs"><button :class="{ active: pane === 'period' }" @click="pane = 'period'">批次维度</button><button :class="{ active: pane === 'account' }" @click="pane = 'account'">账号维度</button></div>
  <section v-if="pane === 'period'" class="card">
    <div class="card-head"><div><h2>批次维度</h2></div></div>
    <div class="card-body"><div class="search-row"><input v-model="cycleQuery" type="search" placeholder="搜索批次周期" /></div></div>
    <div class="table-wrap"><table><thead><tr><th>批次周期</th><th>周期范围</th><th>常规槽位</th><th>营销槽位</th><th>热点槽位</th><th>选题去重数</th><th>选题匹配率</th><th>最近更新时间</th><th>操作</th></tr></thead><tbody>
      <tr v-for="cycle in visibleCycles" :key="cycle.cycle_id"><td><b>{{ cyclePeriodLabel(cycle.cycle_start) }}</b></td><td>{{ cycle.cycle_start }} 至 {{ cycle.cycle_end }}</td><td>{{ cycle.regular_slots }}</td><td>{{ cycle.marketing_slots }}</td><td>{{ cycle.hotspot_slots }}</td><td>{{ cycle.unique_topics }}</td><td>{{ cycle.content_count ? `${Math.round(cycle.topic_uses / cycle.content_count * 100)}%` : '—' }}</td><td>{{ cycle.updated_at }}</td><td><button class="text-btn" type="button" @click="loadCycle(cycle.cycle_id)">批次详情</button></td></tr>
      <tr v-if="visibleCycles.length === 0"><td colspan="9"><div class="empty-state"><b>暂无批次周期</b></div></td></tr>
    </tbody></table></div>
  </section>
  <section v-if="pane === 'detail'" class="card">
    <div class="card-head"><div><h2>批次详情</h2></div><button class="btn" type="button" @click="pane = 'period'">返回批次维度</button></div>
    <div class="card-body"><div class="cycle-detail-filter-grid">
      <label><span>批次周期</span><select v-model="detailCycleId" :disabled="busy || !store.databaseReady" @change="chooseDetailCycle"><option value="">选择批次周期</option><option v-for="cycle in planningCycleSummaries" :key="cycle.cycle_id" :value="cycle.cycle_id">{{ cyclePeriodLabel(cycle.cycle_start) }} · {{ cycle.cycle_start }} 至 {{ cycle.cycle_end }}</option></select></label>
      <label><span>账号</span><select v-model="cycleAccountId"><option value="all">全部账号</option><option v-for="account in cycleAccountOptions" :key="account.account_id" :value="account.account_id">{{ account.account_name }} · {{ account.account_id }}</option></select></label>
      <label><span>槽位类型</span><select v-model="cycleSlotType"><option value="all">全部类型</option><option value="普通">普通</option><option value="营销">营销</option><option value="热点">热点</option></select></label>
      <label><span>内容类型</span><select v-model="cycleContentType"><option value="all">全部内容类型</option><option v-for="value in cycleContentTypes" :key="value" :value="value">{{ value }}</option></select></label>
      <label><span>经营作用</span><select v-model="cycleRole"><option value="all">全部经营作用</option><option v-for="value in cycleRoles" :key="value" :value="value">{{ value }}</option></select></label>
      <label><span>发布状态</span><select v-model="cyclePublishStatus"><option value="all">全部发布状态</option><option v-for="value in cyclePublishStatuses" :key="value" :value="value">{{ value }}</option></select></label>
    </div></div>

    <template v-if="selectedCycle">
    <div class="card-body"><div class="detail-grid"><div><small>参与账号</small><b>{{ selectedCycleStats.accountCount }}</b></div><div><small>总槽位数</small><b>{{ selectedCycleStats.slotCount }}</b></div><div><small>已匹配选题</small><b>{{ selectedCycleStats.matchedCount }} / {{ selectedCycleStats.slotCount }}</b></div><div><small>普通 / 营销 / 热点</small><b>{{ selectedCycleStats.regularCount }} / {{ selectedCycleStats.marketingCount }} / {{ selectedCycleStats.hotspotCount }}</b></div></div></div>
    <div v-if="groupedCycleItems.length" class="batch-account-list planning-account-groups">
      <article v-for="group in pagedGroupedCycleItems" :key="group.account_id" class="batch-account-card planning-account-group">
        <div class="batch-account-head planning-account-group-head">
          <div><div class="batch-account-name"><button class="account-detail-link" type="button" @click="openAccountDetail(group)">{{ group.account_name }}</button><span class="tag gray">{{ group.account_id }}</span><span v-if="group.lifecycle_stage && group.lifecycle_stage !== '—'" class="tag purple">{{ group.lifecycle_stage }}</span></div></div>
          <div class="batch-account-head-actions"><span class="tag blue">{{ group.items.length }} 个策划槽位</span></div>
        </div>
        <div class="table-wrap"><table class="batch-account-items"><thead><tr><th>投放日期</th><th>策划类型</th><th>选题</th><th>选题大纲</th><th>内容类型</th><th>经营作用</th><th>选题类型</th><th>发布状态</th><th>操作</th></tr></thead><tbody>
          <tr v-for="item in group.items" :key="item.id"><td><b>{{ item.publish_date }}</b><small>{{ weekdayLabel(item.publish_date) }} · 阶段：{{ item.lifecycle_stage || '—' }}</small></td><td>{{ item.plan_type === 'auto' ? 'AI自动策划 ' : '手动追加' }}</td><td><b>{{ item.topic_title }}</b></td><td><span :title="item.outline">{{ item.outline || '—' }}</span></td><td>{{ item.content_type || '—' }}</td><td>{{ item.content_role || '—' }}</td><td>{{ topicTypeLabel(item) }}</td><td>{{ item.publish_status }}</td><td class="result-actions"><button v-if="item.allow_replace" class="text-btn" type="button" @click="openReplacement(item)">替换选题</button><button class="text-btn" type="button" @click="openAdjustmentHistory(item)">查看调整记录</button><small v-if="!item.allow_replace && item.replace_block_reason">{{ item.replace_block_reason }}</small></td></tr>
        </tbody></table></div>
      </article>
      <div class="account-pagination">
        <span>共 {{ groupedCycleItems.length }} 个账号</span>
        <label>每页 <select v-model.number="cyclePageSize"><option :value="10">10</option><option :value="20">20</option><option :value="50">50</option></select> 个</label>
        <button class="btn" type="button" :disabled="cyclePage <= 1" @click="cyclePage -= 1">上一页</button>
        <span>{{ cyclePage }} / {{ cyclePageCount }}</span>
        <button class="btn" type="button" :disabled="cyclePage >= cyclePageCount" @click="cyclePage += 1">下一页</button>
      </div>
    </div>
    <div v-else class="empty-state"><b>请选择批次周期</b></div>
    </template>
  </section>
  <section v-if="pane === 'account' && selectedAccount" class="card account-history-filter-card">
    <div class="card-head"><div><h2>筛选策划历史</h2><small>当前 {{ filteredAccountHistory.length }} 个策划槽位</small></div><button class="text-btn" type="button" @click="accountHistoryFrom = ''; accountHistoryTo = ''; accountHistoryCycleId = 'all'">清空筛选</button></div>
    <div class="card-body account-history-toolbar">
      <label><span>账号</span><select :value="accountHistoryAccountId" :disabled="busy" @change="changeHistoryAccount(($event.target as HTMLSelectElement).value)"><option v-if="selectedAccount && !planningAccounts.some(account => account.account_id === selectedAccount?.account_id)" :value="selectedAccount.account_id">{{ selectedAccount.account_name }} · {{ selectedAccount.account_id }}</option><option v-for="account in planningAccounts" :key="account.account_id" :value="account.account_id">{{ account.account_name }} · {{ account.account_id }}</option></select></label>
      <label><span>开始日期</span><input v-model="accountHistoryFrom" type="date" :max="accountHistoryTo || undefined" /></label>
      <label><span>结束日期</span><input v-model="accountHistoryTo" type="date" :min="accountHistoryFrom || undefined" /></label>
      <label><span>批次周期</span><select v-model="accountHistoryCycleId"><option value="all">全部周期</option><option v-for="cycle in accountHistoryCycleOptions" :key="cycle.value" :value="cycle.value">{{ cycle.label }}</option></select></label>
    </div>
    <div v-if="accountHistoryRangeInvalid" class="card-body account-history-filter-error"><small class="inline-error">开始日期不能晚于结束日期。</small></div>
  </section>
  <section v-if="pane === 'account'" class="card">
    <template v-if="selectedAccount">
      <div class="card-head"><div><h2>账号历史</h2><small>{{ selectedAccount.account_name }} · {{ selectedAccount.account_id }}</small><div class="account-history-type-counts"><span>全部 {{ selectedAccount.items.length }} 个槽位</span><span>自动策划 {{ accountHistoryPlanCounts.auto }}</span><span>手动策划 {{ accountHistoryPlanCounts.manual }}</span></div></div><button class="btn" type="button" @click="returnFromAccountDetail">{{ accountReturnPane === 'detail' ? '返回批次详情' : '返回账号列表' }}</button></div>
      <div v-if="accountHistoryGroups.length" class="batch-account-list">
        <article v-for="history in pagedAccountHistoryGroups" :key="history.batch_id ?? history.batch_code" class="batch-account-card account-history-batch">
          <div class="batch-account-head account-history-batch-head"><div><b>{{ cyclePeriodLabel(history.cycle_start) }} · {{ history.cycle_start }} 至 {{ history.cycle_end }}</b><small>{{ history.batch_code }} · {{ history.plan_type === 'auto' ? '自动策划' : '手动策划' }}</small></div><span class="tag blue">{{ history.items.length }} 个策划槽位</span></div>
          <div class="history-slot-grid">
            <article v-for="record in history.items" :key="record.id" class="history-slot-card">
              <div class="history-slot-top"><div class="history-publish-date"><b>{{ record.publish_date }}</b><small>{{ weekdayLabel(record.publish_date) }}<template v-if="record.lifecycle_stage"> · {{ record.lifecycle_stage }}</template></small></div><div class="history-slot-tags"><span class="tag gray">{{ record.plan_type === 'manual' ? '手动策划' : '自动策划' }}</span><span class="tag blue">{{ record.publish_status }}</span></div></div>
              <h3>{{ record.topic_title }}</h3>
              <p class="history-slot-outline">{{ record.outline || '暂无选题大纲' }}</p>
              <div class="history-slot-meta"><div><small>内容类型</small><b>{{ record.content_type || '—' }}</b></div><div><small>经营作用</small><b>{{ record.content_role || '—' }}</b></div><div><small>策划类型</small><b>{{ topicTypeLabel(record) }}</b></div></div>
              <div class="history-slot-actions"><button v-if="record.allow_replace" class="text-btn" type="button" @click="openReplacement(record)">替换选题</button><button class="text-btn" type="button" @click="openAdjustmentHistory(record)">查看调整记录</button><small v-if="!record.allow_replace && record.replace_block_reason">{{ record.replace_block_reason }}</small></div>
            </article>
          </div>
        </article>
        <div class="account-pagination">
          <span>共 {{ accountHistoryGroups.length }} 个批次</span>
          <label>每页 <select v-model.number="accountHistoryPageSize"><option :value="10">10</option><option :value="20">20</option><option :value="50">50</option></select> 个</label>
          <button class="btn" type="button" :disabled="accountHistoryPage <= 1" @click="accountHistoryPage -= 1">上一页</button>
          <span>{{ accountHistoryPage }} / {{ accountHistoryPageCount }}</span>
          <button class="btn" type="button" :disabled="accountHistoryPage >= accountHistoryPageCount" @click="accountHistoryPage += 1">下一页</button>
        </div>
      </div>
      <div v-else-if="!accountHistoryRangeInvalid" class="empty-state"><b>当前筛选范围内暂无策划数据</b></div>
    </template>
    <template v-else>
      <div class="card-head"><div><h2>全部参与策划账号</h2><small>{{ visiblePlanningAccounts.length }} 个账号</small></div></div>
      <div class="card-body"><div class="search-row"><input v-model="accountListQuery" type="search" placeholder="搜索账号名称或 ID" /><span class="muted">共 {{ planningAccounts.length }} 个参与过策划的账号</span></div></div>
      <div class="table-wrap"><table><thead><tr><th>账号</th><th>账号 ID</th><th>参与批次周期数</th><th>历史槽位数</th><th>最近批次周期</th><th>操作</th></tr></thead><tbody>
        <tr v-for="account in visiblePlanningAccounts" :key="account.account_id"><td><button class="account-detail-link" type="button" @click="openPlanningAccount(account)">{{ account.account_name }}</button></td><td>{{ account.account_id }}</td><td>{{ account.cycle_count }}</td><td>{{ account.slot_count }}</td><td>{{ account.latest_cycle_start }}</td><td><button class="text-btn" type="button" @click="openPlanningAccount(account)">查看全部历史</button></td></tr>
        <tr v-if="visiblePlanningAccounts.length === 0"><td colspan="6"><div class="empty-state">{{ planningAccounts.length ? '没有匹配的账号' : '暂无参与策划的账号' }}</div></td></tr>
      </tbody></table></div>
    </template>
  </section>
  <div v-if="replaceTarget" class="drawer-mask" @click.self="closeReplacement">
    <aside class="drawer" role="dialog" aria-modal="true" :aria-label="drawerMode === 'replace' ? '替换选题' : '查看调整记录'">
      <div class="drawer-head"><div><small>{{ drawerMode === 'replace' ? '替换选题' : '查看调整记录' }}</small><h2>{{ replaceTarget.account_name }}</h2></div><button class="icon-btn" type="button" aria-label="关闭" @click="closeReplacement">×</button></div>
      <div class="drawer-body">
        <div class="detail-note"><b>当前选题：</b>{{ replaceTarget.topic_title }}<br /><b>投放日期：</b>{{ replaceTarget.publish_date }}<br /><b>类型：</b>{{ slotLabel(replaceTarget.slot_type, replaceTarget.plan_type) }}<br /><b>状态：</b>{{ replaceTarget.publish_status }}</div>
        <template v-if="drawerMode === 'replace' && replaceTarget.allow_replace">
          <h3>选择新选题</h3>
          <div class="search-row"><input v-model="replacementQuery" type="search" placeholder="按选题标题或内容类型搜索" /></div>
          <div class="topic-check-list"><label v-for="topic in replacementCandidates" :key="topic.topic_id" class="topic-check"><input v-model="replacementTopicId" type="radio" :value="topic.topic_id" name="replacement-topic" /><span><b>{{ topic.topic_title }}</b></span></label></div>
          <div v-if="replacementCandidates.length === 0" class="empty-state">没有可用候选选题</div>
          <label class="field"><span>替换原因（可选）</span><select v-model="replacementReason"><option value="">请选择原因</option><option>原选题与账号不匹配</option><option>选题重复</option><option>内容方向不合适</option><option>业务临时调整</option><option>其他</option></select></label>
        </template>
        <div v-else-if="drawerMode === 'replace'" class="detail-note">{{ replaceTarget.replace_block_reason || '当前记录暂不可替换' }}</div>

        <h3>调整记录</h3>
        <div v-if="adjustmentHistory.length === 0" class="empty-state">暂无历史调整</div>
        <div v-for="record in adjustmentHistory" :key="record.id" class="detail-note">{{ record.created_at }} · {{ record.created_by }} · {{ record.adjustment_source }}<br />{{ record.old_topic_title }} · {{ record.new_topic_title }}<span v-if="record.reason"> · {{ record.reason }}</span></div>
        <div class="footer-actions"><button class="btn" type="button" @click="closeReplacement">关闭</button><button v-if="drawerMode === 'replace' && replaceTarget.allow_replace" class="btn primary" type="button" :disabled="replaceBusy || !replacementTopicId" @click="confirmReplacement">{{ replaceBusy ? '保存中…' : '确认替换' }}</button></div>
      </div>
    </aside>
  </div>
</template>
