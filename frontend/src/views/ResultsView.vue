<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { usePlanningStore } from '../store'
import type { AccountPlanRecord, AdjustmentRecord, PlanningCycleSummary, TopicOption } from '../types'

const store = usePlanningStore()
const route = useRoute()
const pane = ref<'period' | 'detail' | 'account'>('period')
const accountQuery = ref('')
const accountRecords = ref<AccountPlanRecord[]>([])
const accountSearched = ref(false)
const selectedAccount = ref<{ account_id: string; account_name: string; lifecycle_stage: string; items: AccountPlanRecord[] } | null>(null)
const accountHistoryFrom = ref('')
const accountHistoryTo = ref('')
const cycleSummaries = ref<PlanningCycleSummary[]>([])
const periodYear = ref('all')
const periodMonth = ref('all')
const periodWeek = ref('all')
const cycleItems = ref<AccountPlanRecord[]>([])
const selectedCycle = ref<PlanningCycleSummary | null>(null)
const detailCycleId = ref('')
const accountCycleId = ref('')
const accountSelectionId = ref('')
const cycleAccountQuery = ref('')
const cyclePlanType = ref<'all' | 'auto' | 'manual'>('all')
const cycleSlotType = ref('all')
const cycleContentType = ref('all')
const cycleRole = ref('all')
const cyclePublishStatus = ref('all')
const error = ref('')
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
  const value = new Date(`${date}T00:00:00Z`)
  const first = new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), 1))
  const mondayOffset = (first.getUTCDay() + 6) % 7
  return Math.floor((value.getUTCDate() - 1 + mondayOffset) / 7) + 1
}
function cycleWeekKey(date: string) {
  const value = new Date(`${date}T00:00:00Z`)
  return `${value.getUTCFullYear()}-${String(value.getUTCMonth() + 1).padStart(2, '0')}-W${monthWeekOf(date)}`
}
function cyclePeriodLabel(date: string) {
  const value = new Date(`${date}T00:00:00Z`)
  return `${value.getUTCFullYear()}年${value.getUTCMonth() + 1}月第${monthWeekOf(date)}周`
}
const periodYears = computed(() => [...new Set(cycleSummaries.value.map(cycle => cycle.cycle_start.slice(0, 4)))])
const periodMonths = computed(() => [...new Set(cycleSummaries.value.filter(cycle => periodYear.value === 'all' || cycle.cycle_start.startsWith(periodYear.value)).map(cycle => cycle.cycle_start.slice(5, 7)))])
const periodWeeks = computed(() => {
  const months = [...new Set(cycleSummaries.value
    .filter(cycle => periodYear.value === 'all' || cycle.cycle_start.startsWith(periodYear.value))
    .filter(cycle => periodMonth.value === 'all' || cycle.cycle_start.slice(5, 7) === periodMonth.value)
    .map(cycle => cycle.cycle_start.slice(0, 7)))]
  return months.flatMap(month => Array.from({ length: 5 }, (_, index) => {
    const week = index + 1
    return { value: `${month}-W${week}`, label: `${month.slice(0, 4)}年${Number(month.slice(5, 7))}月第${week}周` }
  }))
})
watch([periodYear, periodMonth], () => {
  if (periodWeek.value !== 'all' && !periodWeeks.value.some(week => week.value === periodWeek.value)) periodWeek.value = 'all'
})
const visibleCycleSummaries = computed(() => cycleSummaries.value.filter(cycle =>
  (periodYear.value === 'all' || cycle.cycle_start.startsWith(periodYear.value)) &&
  (periodMonth.value === 'all' || cycle.cycle_start.slice(5, 7) === periodMonth.value) &&
  (periodWeek.value === 'all' || cycleWeekKey(cycle.cycle_start) === periodWeek.value),
))
const accounts = computed(() => visibleCycleSummaries.value.reduce((sum, cycle) => sum + cycle.account_count, 0))
const contents = computed(() => visibleCycleSummaries.value.reduce((sum, cycle) => sum + cycle.content_count, 0))
const successAccounts = computed(() => visibleCycleSummaries.value.reduce((sum, cycle) => sum + cycle.success_accounts, 0))
const completionStatus = computed(() => {
  if (visibleCycleSummaries.value.length === 0) return '暂无记录'
  return visibleCycleSummaries.value.every(cycle => cycle.failed_accounts === 0) ? '已完成' : '未完成'
})
const filteredCycleItems = computed(() => cycleItems.value.filter(item =>
  (!cycleAccountQuery.value.trim() || `${item.account_name} ${item.account_id}`.toLowerCase().includes(cycleAccountQuery.value.trim().toLowerCase())) &&
  (cyclePlanType.value === 'all' || item.plan_type === cyclePlanType.value) &&
  (cycleSlotType.value === 'all' || item.slot_type === cycleSlotType.value) &&
  (cycleContentType.value === 'all' || item.content_type === cycleContentType.value) &&
  (cycleRole.value === 'all' || item.content_role === cycleRole.value) &&
  (cyclePublishStatus.value === 'all' || item.publish_status === cyclePublishStatus.value),
))
const groupedCycleItems = computed(() => {
  const groups = new Map<string, { account_id: string; account_name: string; lifecycle_stage: string; items: AccountPlanRecord[] }>()
  for (const item of filteredCycleItems.value) {
    const key = item.account_id
    const group = groups.get(key)
    if (group) group.items.push(item)
    else groups.set(key, {
      account_id: item.account_id,
      account_name: item.account_name,
      lifecycle_stage: item.lifecycle_stage || '—',
      items: [item],
    })
  }
  return [...groups.values()]
})
const cycleAccounts = computed(() => {
  const groups = new Map<string, { account_id: string; account_name: string; lifecycle_stage: string; items: AccountPlanRecord[] }>()
  for (const item of cycleItems.value) {
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
})
const filteredAccountHistory = computed(() => {
  if (!selectedAccount.value) return []
  return selectedAccount.value.items.filter(item =>
    (!accountHistoryFrom.value || item.publish_date >= accountHistoryFrom.value) &&
    (!accountHistoryTo.value || item.publish_date <= accountHistoryTo.value),
  )
})
const accountHistoryGroups = computed(() => {
  const groups = new Map<string, { cycle_id: string; batch_code: string; cycle_start: string; cycle_end: string; items: AccountPlanRecord[] }>()
  for (const item of filteredAccountHistory.value) {
    const key = item.batch_code
    const group = groups.get(key)
    if (group) group.items.push(item)
    else groups.set(key, { cycle_id: key, batch_code: item.batch_code, cycle_start: item.cycle_start, cycle_end: item.cycle_end, items: [item] })
  }
  return [...groups.values()].sort((a, b) => `${b.cycle_start}-${b.batch_code}`.localeCompare(`${a.cycle_start}-${a.batch_code}`))
})
const cycleContentTypes = computed(() => [...new Set(cycleItems.value.map(item => item.content_type).filter(Boolean))])
const cycleRoles = computed(() => [...new Set(cycleItems.value.map(item => item.content_role).filter((value): value is string => Boolean(value)))])
const cyclePublishStatuses = computed(() => [...new Set(cycleItems.value.map(item => item.publish_status).filter(Boolean))])

function slotLabel(slotType: string, planType: string) {
  if (planType === 'manual') return '手动追加'
  return ({ regular: '常规', marketing_priority: '营销', hotspot: '热点', manual_extra: '手动追加' } as Record<string, string>)[slotType] ?? slotType
}
function weekdayLabel(date: string) {
  return new Intl.DateTimeFormat('zh-CN', { weekday: 'short', timeZone: 'UTC' }).format(new Date(`${date}T00:00:00Z`))
}

const replacementCandidates = computed(() => replacementTopics.value.filter(topic =>
  !replacementQuery.value.trim() || topic.topic_title.includes(replacementQuery.value.trim()),
))
async function openReplacement(item: AccountPlanRecord) {
  drawerMode.value = 'replace'
  replaceTarget.value = item
  replacementQuery.value = ''
  replacementTopicId.value = ''
  replacementReason.value = ''
  adjustmentHistory.value = []
  try {
    const [topics, history] = await Promise.all([api.topics(), api.adjustments(item.id)])
    replacementTopics.value = topics.filter(topic => topic.topic_id !== item.topic_id)
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
    accountRecords.value = update(accountRecords.value)
    if (selectedAccount.value) selectedAccount.value = { ...selectedAccount.value, items: update(selectedAccount.value.items) }
    replaceTarget.value = result.item
    adjustmentHistory.value = await api.adjustments(result.item.id)
    replacementTopicId.value = ''
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '替换失败，当前结果未改变' }
  finally { replaceBusy.value = false }
}
function openAccountDetail(group: { account_id: string; account_name: string; lifecycle_stage: string; items: AccountPlanRecord[] }) {
  selectedAccount.value = group
  accountCycleId.value = selectedCycle.value?.cycle_id || ''
  accountSelectionId.value = group.account_id
  pane.value = 'account'
  void loadAccountHistory(group)
}
async function loadCycle(row: PlanningCycleSummary, targetPane: 'detail' | 'account' = 'detail') {
  if (!store.databaseReady) return
  error.value = ''
  try {
    cycleItems.value = await api.planningCycleItems(row.cycle_id)
    selectedCycle.value = row
    detailCycleId.value = row.cycle_id
    accountCycleId.value = row.cycle_id
    if (targetPane === 'detail') {
      selectedAccount.value = null
      accountSelectionId.value = ''
    }
    pane.value = targetPane
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '????????' }
}
async function openCycle(row: PlanningCycleSummary) { await loadCycle(row, 'detail') }
async function chooseDetailCycle() {
  const row = cycleSummaries.value.find(item => item.cycle_id === detailCycleId.value)
  if (row) await loadCycle(row, 'detail')
}
async function chooseAccountCycle() {
  const row = cycleSummaries.value.find(item => item.cycle_id === accountCycleId.value)
  if (!row) return
  accountSelectionId.value = ''
  selectedAccount.value = null
  await loadCycle(row, 'account')
}
async function loadAccountHistory(group: { account_id: string; account_name: string; lifecycle_stage: string; items: AccountPlanRecord[] }) {
  selectedAccount.value = group
  accountHistoryFrom.value = ''
  accountHistoryTo.value = ''
  pane.value = 'account'
  busy.value = true
  error.value = ''
  try {
    const history = await api.accountItems(group.account_id)
    selectedAccount.value = { ...group, items: history.sort((a, b) => `${b.cycle_start}-${b.publish_date}`.localeCompare(`${a.cycle_start}-${a.publish_date}`)) }
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '读取账号历史失败' }
  finally { busy.value = false }
}
async function chooseAccount() {
  const group = cycleAccounts.value.find(item => item.account_id === accountSelectionId.value)
  if (!group) return
  await loadAccountHistory(group)
}

async function refresh() {
  busy.value = true
  error.value = ''
  try {
    const [, summaries] = await Promise.all([store.refreshBatches(), api.planningCycles()])
    cycleSummaries.value = summaries
  }
  catch (exc) { error.value = exc instanceof Error ? exc.message : '刷新失败' }
  finally { busy.value = false }
}

async function searchAccount() {
  if (!store.databaseReady || !accountQuery.value.trim()) return
  busy.value = true
  error.value = ''
  try {
    accountRecords.value = await api.accountItems(accountQuery.value.trim())
    accountSearched.value = true
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '查询失败' }
  finally { busy.value = false }
}

watch(() => [route.query.batch, cycleSummaries.value.length] as const, async ([id, count]) => {
  if (!count || typeof id !== 'string' || !/^\d+$/.test(id)) return
  try {
    const batch = await api.batch(Number(id))
    const day = new Date(`${batch.cycle_start}T00:00:00Z`)
    day.setUTCDate(day.getUTCDate() - (day.getUTCDay() + 6) % 7)
    const row = cycleSummaries.value.find(item => item.cycle_id === day.toISOString().slice(0, 10))
    if (row) await openCycle(row)
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '读取策划结果失败' }
}, { immediate: true })
watch(() => store.databaseReady, ready => { if (ready) void refresh() }, { immediate: true })
</script>

<template>
  <div class="page-head"><div><h1>策划结果</h1><p>查询策划批次和账号分配记录，查看每条记录的来源与当前状态。</p></div><div class="page-actions"><button class="btn" type="button" :disabled="busy || !store.databaseReady" @click="refresh">{{ busy ? '刷新中…' : '刷新结果' }}</button></div></div>
  <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
  <div class="kpi-grid result-kpi-grid">
    <div class="kpi-card"><small>策划周期</small><strong>{{ cycleSummaries.length }}</strong><span>当前查询范围</span></div>
    <div class="kpi-card"><small>自动策划账号</small><strong>{{ accounts }}</strong><span>各周期合计</span></div>
    <div class="kpi-card"><small>策划条目</small><strong>{{ contents }}</strong><span>AI 自动 + 手动追加</span></div>
    <div class="kpi-card"><small>成功账号</small><strong>{{ successAccounts }}</strong><span>已形成自动策划结果</span></div>
    <div class="kpi-card"><small>完成状态</small><strong class="kpi-text">{{ completionStatus }}</strong><span>系统按兜底规则完成策划</span></div>
  </div>
  <div class="result-tabs"><button :class="{ active: pane === 'period' }" @click="pane = 'period'">周度批次</button><button :class="{ active: pane === 'detail' }" @click="pane = 'detail'">批次详情</button><button :class="{ active: pane === 'account' }" @click="pane = 'account'">账号详情</button></div>
  <section v-if="pane === 'period'" class="card">
    <div class="card-head"><div><h2>周期汇总</h2><small>自动策划账号按周期去重；槽位统计区分 AI 自动策划与手动追加，常规、营销、热点槽位仅统计自动策划槽位。</small></div></div>
    <div class="card-body"><div class="search-row period-filters"><select v-model="periodYear"><option value="all">全部年份</option><option v-for="value in periodYears" :key="value" :value="value">{{ value }} 年</option></select><select v-model="periodMonth"><option value="all">全部月份</option><option v-for="value in periodMonths" :key="value" :value="value">{{ value }} 月</option></select><select v-model="periodWeek"><option value="all">全部周次</option><option v-for="week in periodWeeks" :key="week.value" :value="week.value">{{ week.label }}</option></select></div></div>
    <div class="table-wrap"><table class="period-summary-table"><thead><tr><th>策划周期</th><th>自动策划账号数</th><th>自动策划槽位数</th><th>手动追加槽位数</th><th>总槽位数</th><th>常规槽位数</th><th>营销槽位数</th><th>热点槽位数</th><th>去重选题数</th><th>最后更新时间</th><th>操作</th></tr></thead><tbody>
      <tr v-for="row in visibleCycleSummaries" :key="row.cycle_id"><td><b>{{ cyclePeriodLabel(row.cycle_start) }}</b><small>{{ row.cycle_start }} 至 {{ row.cycle_end }}</small></td><td>{{ row.account_count }}</td><td>{{ row.auto_item_count }}</td><td>{{ row.manual_item_count }}</td><td>{{ row.content_count }}</td><td>{{ row.regular_slots }}</td><td>{{ row.marketing_slots }}</td><td>{{ row.hotspot_slots }}</td><td>{{ row.unique_topics }}</td><td>{{ row.updated_at }}</td><td><button class="text-btn" @click="openCycle(row)">批次详情</button></td></tr>
      <tr v-if="visibleCycleSummaries.length === 0"><td colspan="11"><div class="empty-state"><b>暂无策划周期</b><p>创建批次后会在这里按周期汇总。</p></div></td></tr>
    </tbody></table></div>
  </section>
  <section v-if="pane === 'detail'" class="card">
    <div class="card-head"><div><h2>批次详情</h2><small>{{ selectedCycle ? `${selectedCycle.cycle_start} 至 ${selectedCycle.cycle_end} · 当前有效结果 ` : '请选择要查询的批次' }}</small></div><button class="btn" type="button" @click="pane = 'period'">返回 周度批次</button></div>
    <div class="card-body"><div class="search-row detail-select-row"><select v-model="detailCycleId" :disabled="busy || !store.databaseReady" @change="chooseDetailCycle"><option value="">选择批次</option><option v-for="row in cycleSummaries" :key="row.cycle_id" :value="row.cycle_id">{{ cyclePeriodLabel(row.cycle_start) }}（{{ row.cycle_start }} 至 {{ row.cycle_end }}）</option></select></div></div>
    <div v-if="!selectedCycle" class="empty-state"><b>请先从周度批次打开一个批次</b><p>进入批次详情后可按账号、策划类型、选题类型和发布状态筛选最终有效结果。</p></div>
    <template v-else><div class="card-body"><div class="search-row"><input v-model="cycleAccountQuery" type="search" placeholder="搜索账号名称或 ID" /><select v-model="cyclePlanType"><option value="all">全部策划类型</option><option value="auto">AI自动策划</option><option value="manual">手动策划</option></select><select v-model="cycleSlotType"><option value="all">全部选题类型</option><option value="regular">普通</option><option value="marketing_priority">营销</option><option value="hotspot">热点</option><option value="manual_extra">手动追加</option></select><select v-model="cycleContentType"><option value="all">全部内容类型</option><option v-for="value in cycleContentTypes" :key="value" :value="value">{{ value }}</option></select><select v-model="cycleRole"><option value="all">全部经营作用</option><option v-for="value in cycleRoles" :key="value" :value="value">{{ value }}</option></select><select v-model="cyclePublishStatus"><option value="all">全部发布状态</option><option v-for="value in cyclePublishStatuses" :key="value" :value="value">{{ value }}</option></select></div></div>
    <div v-if="groupedCycleItems.length" class="batch-account-list">
      <article v-for="group in groupedCycleItems" :key="group.account_id" class="batch-account-card">
        <div class="batch-account-head">
          <div><div class="batch-account-name"><button class="account-detail-link" type="button" @click="openAccountDetail(group)">{{ group.account_name }}</button><span class="tag gray">{{ group.account_id }}</span></div><div class="batch-account-stage">经营阶段：{{ group.lifecycle_stage }}</div></div>
          <span class="tag blue">{{ group.items.length }} 个策划槽位</span>
        </div>
        <div class="table-wrap"><table class="batch-account-items"><thead><tr><th>投放日期</th><th>策划类型</th><th>选题</th><th>选题大纲</th><th>内容类型</th><th>经营作用</th><th>选题类型</th><th>发布状态</th><th>操作</th></tr></thead><tbody>
          <tr v-for="item in group.items" :key="item.id"><td><b>{{ item.publish_date }}</b><small>{{ weekdayLabel(item.publish_date) }}</small></td><td>{{ item.plan_type === 'auto' ? 'AI自动策划 ' : '手动追加' }}</td><td><b>{{ item.topic_title }}</b></td><td><span :title="item.outline">{{ item.outline || '?' }}</span></td><td>{{ item.content_type || '?' }}</td><td>{{ item.content_role || '?' }}</td><td>{{ item.topic_type || slotLabel(item.slot_type, item.plan_type) }}</td><td>{{ item.publish_status }}</td><td class="result-actions"><button v-if="item.allow_replace" class="text-btn" type="button" @click="openReplacement(item)">替换选题</button><button v-if="item.plan_type === 'auto'" class="text-btn" type="button" @click="openAdjustmentHistory(item)">查看调整记录</button><small v-if="!item.allow_replace && item.plan_type === 'auto'">{{ item.replace_block_reason }}</small></td></tr>
        </tbody></table></div>
      </article>
    </div>
    <div v-else class="empty-state"><b>当前筛选下没有匹配结果</b></div></template>
  </section>
  <section v-if="pane === 'account'" class="card">
    <template v-if="selectedAccount">
      <div class="card-head"><div><h2>账号详情</h2><small>{{ selectedAccount.account_name }} ? {{ selectedAccount.account_id }} ? 历史策划批次</small></div><button class="btn" type="button" @click="selectedAccount = null; pane = 'detail'">返回批次详情</button></div>
      <div class="card-body"><div class="account-detail-summary"><span class="tag gray">{{ selectedAccount.account_id }}</span><span class="tag blue">{{ filteredAccountHistory.length }} 个策划槽位</span><label class="date-filter"><span>开始日期</span><input v-model="accountHistoryFrom" type="date" /></label><label class="date-filter"><span>结束日期</span><input v-model="accountHistoryTo" type="date" /></label><button class="text-btn" type="button" @click="accountHistoryFrom = ''; accountHistoryTo = ''">清空时间筛选</button></div></div>
      <div v-if="accountHistoryGroups.length" class="batch-account-list">
        <article v-for="history in accountHistoryGroups" :key="history.cycle_id" class="batch-account-card">
          <div class="batch-account-head"><div><b>{{ history.cycle_start }} ? {{ history.cycle_end }}</b><small>{{ history.batch_code }}</small></div><span class="tag blue">{{ history.items.length }} 个策划槽位</span></div>
          <div class="table-wrap"><table class="batch-account-items"><thead><tr><th>投放日期</th><th>策划类型</th><th>选题</th><th>选题大纲</th><th>内容类型</th><th>经营作用</th><th>选题类型</th><th>发布状态</th><th>操作</th></tr></thead><tbody>
            <tr v-for="record in history.items" :key="record.id"><td><b>{{ record.publish_date }}</b><small>{{ weekdayLabel(record.publish_date) }}</small></td><td>{{ record.plan_type === 'manual' ? '手动策划' : 'AI自动策划' }}</td><td><b>{{ record.topic_title }}</b></td><td><span :title="record.outline">{{ record.outline || '?' }}</span></td><td>{{ record.content_type || '?' }}</td><td>{{ record.content_role || '?' }}</td><td>{{ record.topic_type || slotLabel(record.slot_type, record.plan_type) }}</td><td>{{ record.publish_status }}</td><td class="result-actions"><button v-if="record.allow_replace" class="text-btn" type="button" @click="openReplacement(record)">替换选题</button><button v-if="record.plan_type === 'auto'" class="text-btn" type="button" @click="openAdjustmentHistory(record)">查看调整记录</button><small v-if="!record.allow_replace && record.plan_type === 'auto'">{{ record.replace_block_reason }}</small></td></tr>
          </tbody></table></div>
        </article>
      </div>
      <div v-else class="empty-state"><b>该时间范围内暂无策划数据</b></div>
    </template>
    <template v-else>
      <div class="card-head"><div><h2>账号详情</h2><small>可直接选择批次和账号查询，不需要从批次详情进入</small></div></div>
      <div class="card-body"><div class="search-row detail-select-row"><select v-model="accountCycleId" :disabled="busy || !store.databaseReady" @change="chooseAccountCycle"><option value="">选择批次</option><option v-for="row in cycleSummaries" :key="row.cycle_id" :value="row.cycle_id">{{ cyclePeriodLabel(row.cycle_start) }}（{{ row.cycle_start }} 至 {{ row.cycle_end }}）</option></select><select v-model="accountSelectionId" :disabled="!selectedCycle || cycleAccounts.length === 0" @change="chooseAccount"><option value="">选择账号</option><option v-for="group in cycleAccounts" :key="group.account_id" :value="group.account_id">{{ group.account_name }}（{{ group.account_id }}）</option></select></div></div>
      <div v-if="!selectedCycle" class="empty-state"><b>请选择批次</b><p>选择批次后，再选择账号查看该批次的账号详情。</p></div>
      <div v-else-if="cycleAccounts.length === 0" class="empty-state"><b>当前批次暂无账号结果</b></div>
    </template>
  </section>
  <div v-if="replaceTarget" class="drawer-mask" @click.self="closeReplacement">
    <aside class="drawer" role="dialog" aria-modal="true" :aria-label="drawerMode === 'replace' ? '替换选题' : '查看调整记录'">
      <div class="drawer-head"><div><small>{{ drawerMode === 'replace' ? '替换选题' : '查看调整记录' }}</small><h2>{{ replaceTarget.account_name }}</h2></div><button class="icon-btn" type="button" aria-label="关闭" @click="closeReplacement">×</button></div>
      <div class="drawer-body">
        <div class="detail-note"><b>当前选题：</b>{{ replaceTarget.topic_title }}<br /><b>投放日期：</b>{{ replaceTarget.publish_date }}<br /><b>类型：</b>{{ slotLabel(replaceTarget.slot_type, replaceTarget.plan_type) }}<br /><b>状态：</b>{{ replaceTarget.publish_status }}</div>
        <template v-if="drawerMode === 'replace' && replaceTarget.allow_replace">
          <h3>选择新选题</h3>
          <div class="search-row"><input v-model="replacementQuery" type="search" placeholder="按标题关键词搜索" /></div>
          <div class="topic-check-list"><label v-for="topic in replacementCandidates" :key="topic.topic_id" class="topic-check"><input v-model="replacementTopicId" type="radio" :value="topic.topic_id" name="replacement-topic" /><span><b>{{ topic.topic_title }}</b><small>{{ topic.content_type || '内容类型暂无资料' }}<template v-if="topic.outline"> · {{ topic.outline }}</template></small></span></label></div>
          <div v-if="replacementCandidates.length === 0" class="empty-state">没有可用候选选题</div>
          <label class="field"><span>替换原因（可选）</span><select v-model="replacementReason"><option value="">请选择原因</option><option>原选题与账号不匹配</option><option>选题重复</option><option>内容方向不合适</option><option>业务临时调整</option><option>其他</option></select></label>
        </template>
        <div v-else-if="drawerMode === 'replace'" class="detail-note">{{ replaceTarget.replace_block_reason || '当前记录暂不可替换' }}</div>
        <div v-if="drawerMode === 'history'" class="detail-note">当前为只读模式，仅查看本条记录的调整历史。</div>
        <h3>调整记录</h3>
        <div v-if="adjustmentHistory.length === 0" class="empty-state">暂无历史调整</div>
        <div v-for="record in adjustmentHistory" :key="record.id" class="detail-note">{{ record.created_at }} · {{ record.adjustment_source }}<br />{{ record.old_topic_title }} · {{ record.new_topic_title }}<span v-if="record.reason"> · {{ record.reason }}</span></div>
        <div class="footer-actions"><button class="btn" type="button" @click="closeReplacement">关闭</button><button v-if="drawerMode === 'replace' && replaceTarget.allow_replace" class="btn primary" type="button" :disabled="replaceBusy || !replacementTopicId" @click="confirmReplacement">{{ replaceBusy ? '保存中?' : '确认替换' }}</button></div>
      </div>
    </aside>
  </div>
</template>
