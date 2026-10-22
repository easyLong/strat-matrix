<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import AccountTypeBadge from '../components/AccountTypeBadge.vue'
import LoadingSkeleton from '../components/LoadingSkeleton.vue'
import ListPagination from '../components/ListPagination.vue'
import HoverHint from '../components/HoverHint.vue'
import ContentFlowDrawer from '../components/ContentFlowDrawer.vue'
import ResultsView from './ResultsView.vue'
import { api } from '../api'
import type { AccountOption, AccountPlanRecord, BatchDetail, BatchSummary } from '../types'
import { statusTone } from '../ui/status'
import { productionStatusLabel } from '../ui/slotContentStatus'
import { summarizeContentTypes } from '../ui/contentTypeStats'

type DetailMode = 'batch' | 'cycle' | 'account'
type PlanningWeek = { start: string; end: string; items: AccountPlanRecord[] }
type AccountGroup = {
  account_id: string
  account_name: string
  lifecycle_stage: string
  profile?: AccountOption
  items: AccountPlanRecord[]
}

const props = withDefaults(defineProps<{
  mode?: DetailMode
  cycleStart: string
  cycleEnd: string
  batches: BatchSummary[]
  accountId?: string
  returnLabel?: string
}>(), { mode: 'cycle', accountId: '', returnLabel: '' })

const emit = defineEmits<{
  back: []
}>()

const loading = ref(false)
const error = ref('')
const details = ref<BatchDetail[]>([])
const historyItems = ref<AccountPlanRecord[]>([])
const accountCatalog = ref<AccountOption[]>([])
const expandedAccounts = ref(new Set<string>())
const filtersExpanded = ref(false)
const accountKeyword = ref('')
const contentType = ref('all')
const selectedPlan = ref<AccountPlanRecord | null>(null)
const cycleFilter = ref('all')
const appliedFilters = ref({ account: '', cycle: 'all', batch: 'all', planType: 'all', contentType: 'all' })
const page = ref(1)
const pageSize = ref(20)
const historyPage = ref(1)
const historyPageSize = ref(20)
let loadRequest = 0

const isBatchMode = computed(() => props.mode === 'batch')
const isAccountMode = computed(() => props.mode === 'account')
const detailTitle = computed(() => isAccountMode.value ? '账号策划详情' : isBatchMode.value ? '批次策划详情' : '周期策划详情')
const currentBatch = computed(() => isBatchMode.value ? props.batches[0] ?? null : null)
const batchById = computed(() => new Map(props.batches.map(batch => [batch.id, batch])))
const contentFlowBatchId = ref<number | null>(null)
const productionItems = computed(() => details.value.flatMap(detail => detail.items))
const backLabel = computed(() => props.returnLabel || (isAccountMode.value ? '返回账号列表' : '返回时间列表'))
const fixedPlanType = computed<'auto' | 'manual' | null>(() => isBatchMode.value ? currentBatch.value?.plan_type ?? null : null)
const scopeLabel = computed(() => {
  if (isAccountMode.value) return `${accountProfile(props.accountId)?.account_name || historyItems.value[0]?.account_name || props.accountId} · ${props.accountId}`
  if (currentBatch.value) return [currentBatch.value.task_name, currentBatch.value.batch_code].filter(Boolean).join(' · ')
  return cyclePeriodLabel(props.cycleStart)
})
const scopePlanType = computed(() => {
  return fixedPlanType.value === 'manual' ? '人工策划' : 'AI 自动策划'
})

function weekStart(value: string) {
  const date = new Date(`${value}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7)
  return date.toISOString().slice(0, 10)
}

function weekEnd(value: string) {
  const date = new Date(`${weekStart(value)}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + 6)
  return date.toISOString().slice(0, 10)
}

function cyclePeriodLabel(value: string) {
  if (!value) return '全部周期'
  const date = new Date(`${weekStart(value)}T00:00:00Z`)
  return `${date.getUTCFullYear()}年${date.getUTCMonth() + 1}月第${Math.floor((date.getUTCDate() - 1) / 7) + 1}周`
}

function accountProfile(accountId: string) {
  return accountCatalog.value.find(account => account.account_id === accountId)
}

function accountTypeLabel(profile?: AccountOption) {
  return profile?.account_type || (profile?.certified === true ? '认证' : profile?.certified === false ? '非认证' : '—')
}

function topicTypeLabel(item: AccountPlanRecord) {
  if (!item.topic_id) return '待确定'
  const type = String(item.topic_type ?? '')
  if (type === '营销' || type === 'marketing' || type === 'marketing_priority') return '营销'
  if (type === '热点' || type === 'hotspot') return '热点'
  return '普通'
}

function weekdayLabel(date: string) {
  return new Intl.DateTimeFormat('zh-CN', { weekday: 'short', timeZone: 'UTC' }).format(new Date(`${date}T00:00:00Z`))
}

function sourceLabel(item: AccountPlanRecord) {
  return item.plan_type === 'manual' ? '人' : 'AI'
}

function sourceHint(item: AccountPlanRecord) {
  return item.plan_type === 'manual' ? '人：人工策划' : 'AI：自动策划'
}

const allItems = computed<AccountPlanRecord[]>(() => isAccountMode.value ? historyItems.value : details.value.flatMap(batch => batch.items.map(item => ({
  ...item,
  batch_id: batch.id,
  batch_code: batch.batch_code,
  batch_created_at: batch.created_at,
  plan_type: batch.plan_type,
  cycle_start: batch.cycle_start,
  cycle_end: batch.cycle_end,
}))))

const contentTypes = computed(() => [...new Set(allItems.value.map(item => item.content_type).filter(Boolean))].sort())
const cycleOptions = computed(() => [...new Set(allItems.value.map(item => weekStart(item.publish_date)))].sort().reverse())
const filteredItems = computed(() => {
  const filters = appliedFilters.value
  const keyword = filters.account.trim().toLocaleLowerCase()
  return allItems.value.filter(item =>
    (!keyword || `${item.account_name} ${item.account_id}`.toLocaleLowerCase().includes(keyword)) &&
    (filters.cycle === 'all' || weekStart(item.publish_date) === filters.cycle) &&
    (filters.batch === 'all' || String(item.batch_id) === filters.batch) &&
    (filters.planType === 'all' || item.plan_type === filters.planType) &&
    (filters.contentType === 'all' || item.content_type === filters.contentType),
  )
})

const accountGroups = computed<AccountGroup[]>(() => {
  const groups = new Map<string, AccountGroup>()
  for (const item of filteredItems.value) {
    const existing = groups.get(item.account_id)
    if (existing) existing.items.push(item)
    else groups.set(item.account_id, {
      account_id: item.account_id,
      account_name: item.account_name,
      lifecycle_stage: item.lifecycle_stage || '—',
      profile: accountProfile(item.account_id),
      items: [item],
    })
  }
  return [...groups.values()]
    .map(group => ({ ...group, items: group.items.sort((a, b) => a.publish_date.localeCompare(b.publish_date) || a.id - b.id) }))
    .sort((a, b) => a.account_name.localeCompare(b.account_name, 'zh-CN'))
})

const dashboard = computed(() => ({
  accounts: new Set(filteredItems.value.map(item => item.account_id)).size,
  batches: new Set(filteredItems.value.map(item => item.batch_id)).size,
  topics: new Set(filteredItems.value.map(item => item.topic_id).filter(Boolean)).size,
  plans: filteredItems.value.length,
  autoPlans: filteredItems.value.filter(item => item.plan_type === 'auto').length,
  manualPlans: filteredItems.value.filter(item => item.plan_type === 'manual').length,
}))
const topicTypeCounts = computed(() => summarizeContentTypes(filteredItems.value))

const pagedAccountGroups = computed(() => accountGroups.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const accountHistoryRows = computed(() => [...filteredItems.value].sort((a, b) =>
  b.publish_date.localeCompare(a.publish_date) || b.batch_id - a.batch_id || b.id - a.id,
))
const pagedAccountHistoryRows = computed(() => accountHistoryRows.value.slice(
  (historyPage.value - 1) * historyPageSize.value,
  historyPage.value * historyPageSize.value,
))

function weeksFor(group: AccountGroup): PlanningWeek[] {
  const weeks = new Map<string, AccountPlanRecord[]>()
  for (const item of group.items) {
    const key = weekStart(item.publish_date)
    const items = weeks.get(key)
    if (items) items.push(item)
    else weeks.set(key, [item])
  }
  return [...weeks].map(([start, items]) => ({ start, end: weekEnd(start), items })).sort((a, b) => b.start.localeCompare(a.start))
}

function daysFor(week: PlanningWeek) {
  const start = new Date(`${week.start}T00:00:00Z`)
  return Array.from({ length: 7 }, (_, offset) => {
    const date = new Date(start)
    date.setUTCDate(start.getUTCDate() + offset)
    const value = date.toISOString().slice(0, 10)
    return {
      date: value,
      label: value.slice(5),
      weekday: weekdayLabel(value),
      items: week.items.filter(item => item.publish_date === value),
    }
  })
}

function toggleAccount(accountId: string) {
  const next = new Set(expandedAccounts.value)
  if (next.has(accountId)) next.delete(accountId)
  else next.add(accountId)
  expandedAccounts.value = next
}

function updatePlan(item: AccountPlanRecord) {
  historyItems.value = historyItems.value.map(record => record.id === item.id ? { ...record, ...item } : record)
  details.value = details.value.map(batch => ({
    ...batch,
    items: batch.items.map(record => record.id === item.id ? { ...record, ...item } : record),
  }))
}

async function load(silent = false) {
  const request = ++loadRequest
  if (!silent) loading.value = true
  error.value = ''
  try {
    const [records, accounts] = await Promise.allSettled([
      isAccountMode.value ? api.accountItems(props.accountId) : Promise.all(props.batches.map(batch => api.batch(batch.id))),
      silent && accountCatalog.value.length ? Promise.resolve(accountCatalog.value) : api.accounts(1000, true),
    ])
    if (request !== loadRequest) return
    if (records.status === 'rejected') throw records.reason
    if (isAccountMode.value) historyItems.value = records.value as AccountPlanRecord[]
    else details.value = records.value as BatchDetail[]
    if (accounts.status === 'fulfilled') accountCatalog.value = accounts.value
    if (isAccountMode.value) expandedAccounts.value = new Set([props.accountId])
  } catch (exc) {
    if (request === loadRequest) error.value = exc instanceof Error ? exc.message : '读取策划明细失败'
  } finally {
    if (request === loadRequest) loading.value = false
  }
}

function applyFilters() {
  appliedFilters.value = {
    account: isAccountMode.value ? '' : accountKeyword.value,
    cycle: isAccountMode.value ? cycleFilter.value : 'all',
    batch: isBatchMode.value ? String(currentBatch.value?.id) : 'all',
    planType: fixedPlanType.value ?? 'all',
    contentType: contentType.value,
  }
  page.value = 1
  historyPage.value = 1
}

watch([() => props.mode, () => props.accountId, () => props.cycleStart, () => props.batches.map(batch => batch.id).join(',')], () => {
  accountKeyword.value = ''
  contentType.value = 'all'
  cycleFilter.value = isAccountMode.value ? props.cycleStart || 'all' : props.cycleStart
  filtersExpanded.value = false
  applyFilters()
  expandedAccounts.value = new Set()
  selectedPlan.value = null
  void load()
}, { immediate: true })
watch(pageSize, () => { page.value = 1 })
watch(historyPageSize, () => { historyPage.value = 1 })
const productionTimer = window.setInterval(() => {
  if (!loading.value && productionItems.value.some(item => item.topic_id && ['待生产', '生产中'].includes(productionStatusLabel(item)))) void load(true)
}, 3000)
onBeforeUnmount(() => { loadRequest++; window.clearInterval(productionTimer) })
</script>

<template>
  <ContentFlowDrawer v-if="contentFlowBatchId" :batch-id="contentFlowBatchId" @close="contentFlowBatchId = null" @changed="load(true)" />
  <section class="card planning-detail-card">
    <div class="card-head planning-detail-head">
      <div class="planning-detail-heading">
        <h2>{{ detailTitle }}</h2>
        <div v-if="isBatchMode" class="planning-detail-scope planning-batch-scope">
          <HoverHint text="周期" :show-icon="false" class="tag gray planning-context-tag">{{ cyclePeriodLabel(cycleStart) }}</HoverHint>
          <HoverHint text="策划方式" :show-icon="false" :class="['tag', 'planning-context-tag', fixedPlanType === 'manual' ? 'orange' : 'blue']">{{ scopePlanType }}</HoverHint>
          <HoverHint text="批次号" :show-icon="false" class="tag gray planning-context-tag"><span class="planning-batch-code">{{ currentBatch?.batch_code || '—' }}</span></HoverHint>
        </div>
        <div v-else-if="isAccountMode" class="planning-detail-scope">
          <HoverHint text="账号" :show-icon="false" class="tag gray planning-context-tag"><span class="planning-scope-label">{{ scopeLabel }}</span></HoverHint>
          <HoverHint text="周期" :show-icon="false" class="tag gray planning-context-tag">{{ appliedFilters.cycle === 'all' ? '全部周期' : cyclePeriodLabel(appliedFilters.cycle) }}</HoverHint>
        </div>
        <div v-else class="planning-detail-scope"><HoverHint text="周期" :show-icon="false" class="tag gray planning-context-tag">{{ scopeLabel }}</HoverHint></div>
      </div>
      <div class="planning-detail-actions">
        <button v-if="isBatchMode && currentBatch" class="btn" type="button" @click="contentFlowBatchId = currentBatch.id">查看内容流水</button>
        <button class="btn" type="button" @click="emit('back')">{{ backLabel }}</button>
      </div>
    </div>

    <LoadingSkeleton v-if="loading" :rows="8" />
    <div v-else-if="error" class="banner error-banner" role="alert">{{ error }}</div>
    <template v-else>
      <section class="planning-dashboard" aria-label="策划概览">
        <div><small>账号数</small><strong>{{ dashboard.accounts }}</strong></div>
        <div><small>{{ isBatchMode ? '选题数' : '批次数' }}</small><strong>{{ isBatchMode ? dashboard.topics : dashboard.batches }}</strong></div>
        <div><small>策划总数</small><strong>{{ dashboard.plans }}</strong></div>
        <div><small>AI 策划</small><strong>{{ dashboard.autoPlans }}</strong></div>
        <div><small>人工策划</small><strong>{{ dashboard.manualPlans }}</strong></div>
      </section>

      <section v-if="isBatchMode" class="batch-topic-types" aria-labelledby="batch-topic-types-title">
        <h3 id="batch-topic-types-title">选题内容类型</h3>
        <dl>
          <div v-for="type in topicTypeCounts" :key="type.name" :title="type.hint">
            <dt>{{ type.name }}</dt><dd :class="{ empty: type.count === 0 }">{{ type.count }}</dd>
          </div>
        </dl>
      </section>

      <div class="detail-filter-shell">
        <button class="filter-collapse-toggle" type="button" :aria-expanded="filtersExpanded" @click="filtersExpanded = !filtersExpanded">
          <span>筛选条件</span>
          <svg :class="{ expanded: filtersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg>
        </button>
        <div v-show="filtersExpanded" class="detail-filter-fields query-filter-grid" data-query-filters="compact">
          <label v-if="!isAccountMode"><span>账号 ID 或昵称</span><input v-model="accountKeyword" type="search" placeholder="输入账号 ID 或昵称" /></label>
          <label v-if="isAccountMode"><span>周期</span><select v-model="cycleFilter"><option value="all">全部周期</option><option v-for="value in cycleOptions" :key="value" :value="value">{{ cyclePeriodLabel(value) }}</option></select></label>
          <div class="query-filter-tail">
                <label><span>内容类型</span><select v-model="contentType"><option value="all">全部内容类型</option><option v-for="value in contentTypes" :key="value" :value="value">{{ value }}</option></select></label>
                <div class="query-filter-actions"><button class="btn primary detail-query-btn" type="button" @click="applyFilters">查询</button></div>
              </div>
        </div>
      </div>

      <template v-if="isAccountMode">
        <div class="table-wrap account-plan-table-wrap">
          <table class="account-plan-table" aria-label="账号策划列表">
            <colgroup><col style="width:155px" /><col style="width:20%" /><col /><col style="width:90px" /><col style="width:110px" /><col style="width:240px" /><col style="width:100px" /></colgroup>
            <thead><tr><th scope="col">投放日期 / 星期</th><th scope="col">选题标题</th><th scope="col">选题大纲</th><th scope="col">内容类型</th><th scope="col">策划方式</th><th scope="col">批次信息</th><th scope="col">内容状态</th></tr></thead>
            <tbody>
              <tr v-for="item in pagedAccountHistoryRows" :key="item.id">
                <td class="account-plan-date">{{ item.publish_date }} {{ weekdayLabel(item.publish_date) }}</td>
                <td class="account-plan-text">{{ item.topic_title || (item.topic_id ? '暂无选题标题' : '待定题') }}</td>
                <td class="account-plan-text">{{ item.outline || '—' }}</td>
                <td>{{ item.content_type || '—' }}</td>
                <td>{{ item.plan_type === 'manual' ? '人工策划' : '自动策划' }}</td>
                <td class="account-plan-batch"><span>{{ batchById.get(item.batch_id)?.task_name || '未命名批次' }}</span><small>{{ item.batch_code || batchById.get(item.batch_id)?.batch_code || '—' }}</small></td>
                <td>{{ productionStatusLabel(item) }}</td>
              </tr>
              <tr v-if="!accountHistoryRows.length"><td colspan="7" class="empty-state">暂无策划记录</td></tr>
            </tbody>
          </table>
        </div>
        <ListPagination v-if="accountHistoryRows.length" v-model:page="historyPage" v-model:page-size="historyPageSize" :total="accountHistoryRows.length" unit="条" class="list-pagination-inset" />
      </template>
      <div v-else-if="accountGroups.length" class="planning-account-list">
        <article v-for="group in pagedAccountGroups" :key="group.account_id" :class="['planning-account-card', { expanded: expandedAccounts.has(group.account_id) }]">
          <header class="planning-account-head">
            <div class="planning-account-main">
              <div class="planning-account-identity">
                <div class="planning-account-title">
                  <strong>{{ group.account_name }}</strong>
                  <AccountTypeBadge :type="accountTypeLabel(group.profile)" />
                  <span v-if="group.lifecycle_stage && group.lifecycle_stage !== '—'" class="tag purple">{{ group.lifecycle_stage }}</span>
                </div>
                <div class="planning-account-meta">
                  <span>{{ group.account_id }}</span>
                  <span v-if="group.profile?.organization">{{ group.profile.organization }}</span>
                  <span v-if="group.profile?.um_no">UM {{ group.profile.um_no }}</span>
                  <span v-if="group.profile?.platform">{{ group.profile.platform }}</span>
                  <span class="planning-account-persona-inline"><b>人设</b>{{ group.profile?.persona || '未配置' }}</span>
                </div>
              </div>
            </div>
            <div class="planning-account-actions">
              <span class="planning-plan-count">{{ group.items.length }} 条策划</span>
              <button class="planning-expand-btn" type="button" :aria-expanded="expandedAccounts.has(group.account_id)" :aria-label="`${expandedAccounts.has(group.account_id) ? '收起' : '展开'}${group.account_name}的策划计划`" @click="toggleAccount(group.account_id)">
                <span>{{ expandedAccounts.has(group.account_id) ? '收起' : '展开' }}</span>
                <svg :class="{ expanded: expandedAccounts.has(group.account_id) }" width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg>
              </button>
            </div>
          </header>

          <template v-if="expandedAccounts.has(group.account_id)">
          <div v-for="week in weeksFor(group)" :key="week.start" class="planning-week-section">
            <div class="planning-week-heading"><HoverHint :text="`${week.start} 至 ${week.end}`" :show-icon="false">{{ cyclePeriodLabel(week.start) }}</HoverHint><span>{{ week.items.length }} 条策划</span></div>
          <div class="planning-week-wrap">
            <div class="planning-week-grid">
              <section v-for="day in daysFor(week)" :key="day.date" class="planning-day">
                <header><div><b>{{ day.label }}</b><small>{{ day.weekday }}</small></div><span>{{ day.items.length }} 条</span></header>
                <div v-if="day.items.length" class="planning-day-items">
                  <button v-for="item in day.items" :key="item.id" type="button" class="planning-plan-card navigable" :aria-label="`查看计划详情：${item.topic_title || '待确定选题'}`" @click="selectedPlan = item">
                    <div class="account-week-plan-tags">
                      <span :class="['tag', 'gray', 'planning-source-badge', item.plan_type === 'manual' ? 'source-manual' : 'source-ai']" :data-source-hint="sourceHint(item)" :aria-label="sourceHint(item)" tabindex="0">{{ sourceLabel(item) }}</span>
                      <span :class="['tag', statusTone(productionStatusLabel(item))]">{{ productionStatusLabel(item) }}</span>
                    </div>
                    <b>{{ item.topic_title || '待确定选题' }}</b>
                    <small>{{ item.content_type || '—' }} · {{ topicTypeLabel(item) }}</small>
                    <span v-if="!isBatchMode" class="planning-plan-batch">{{ item.batch_code }}</span>
                  </button>
                </div>
                <div v-else class="planning-day-empty">暂无计划</div>
              </section>
            </div>
          </div>
          </div>
          </template>
        </article>
      </div>
      <div v-else class="empty-state"><b>当前筛选条件下暂无策划结果</b></div>
      <ListPagination v-if="!isAccountMode && accountGroups.length" v-model:page="page" v-model:page-size="pageSize" :total="accountGroups.length" unit="个账号" class="list-pagination-inset" />
    </template>
  </section>
  <ResultsView v-if="selectedPlan" detail-only :plan="selectedPlan" :profiles="accountCatalog" @close-plan="selectedPlan = null" @plan-updated="updatePlan" />
</template>

<style scoped>
.batch-topic-types{margin:0 20px 16px;padding:0 0 4px}.batch-topic-types h3{margin:0 0 8px;color:var(--neutral-700);font-size:13px;line-height:22px;font-weight:600}.batch-topic-types dl{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));column-gap:20px;margin:0}.batch-topic-types dl>div{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0;padding:9px 0;border-bottom:1px solid var(--neutral-100)}.batch-topic-types dt{color:var(--neutral-500);font-size:12px;line-height:20px;overflow-wrap:anywhere}.batch-topic-types dd{flex:none;margin:0;color:var(--neutral-800);font-size:14px;line-height:20px;font-weight:500;font-variant-numeric:tabular-nums}.batch-topic-types dd.empty{color:var(--neutral-400);font-weight:400}
@media(max-width:1200px){.batch-topic-types dl{grid-template-columns:repeat(4,minmax(0,1fr))}}@media(max-width:980px){.batch-topic-types{margin:0 12px 16px}.batch-topic-types dl{grid-template-columns:repeat(3,minmax(0,1fr));column-gap:16px}}@media(max-width:580px){.batch-topic-types dl{grid-template-columns:repeat(2,minmax(0,1fr));column-gap:12px}}
.account-plan-table-wrap{margin:0 20px 20px}.account-plan-table{table-layout:fixed;min-width:1180px}.account-plan-table th,.account-plan-table td{padding:14px 12px;vertical-align:top;line-height:22px}.account-plan-table td{color:var(--neutral-700)}.account-plan-date{white-space:nowrap;font-variant-numeric:tabular-nums}.account-plan-text{white-space:pre-wrap;overflow-wrap:anywhere}.account-plan-batch{overflow-wrap:anywhere}.account-plan-batch>span{display:block}.account-plan-batch>small{margin-top:3px;font-size:12px;line-height:18px}.account-plan-table .empty-state{text-align:center;padding:32px 12px;color:var(--neutral-400)}
@media(max-width:980px){.account-plan-table-wrap{margin:0 12px 16px}}
.planning-detail-head{align-items:flex-start;flex-wrap:wrap}.planning-detail-heading{flex:1 1 260px;min-width:0}.planning-detail-actions{display:flex;flex:0 0 auto;align-items:center;align-self:flex-start;justify-content:flex-end;flex-wrap:wrap;gap:8px;max-width:100%;margin-left:auto}.planning-detail-actions .btn{white-space:nowrap}.planning-detail-scope .planning-context-tag{min-width:0;max-width:100%;min-height:24px;padding:3px 8px;border-radius:6px;background:var(--neutral-100);color:var(--neutral-500);font-size:12px;line-height:18px;font-weight:500}.planning-batch-code{min-width:0;max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.planning-batch-scope .planning-context-tag.orange{background:var(--processing-bg);color:var(--processing)}.planning-batch-scope .planning-context-tag.blue{background:var(--primary-50);color:var(--primary-600)}
.planning-detail-scope{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-top:6px;min-width:0}.planning-scope-label{max-width:560px;overflow:hidden;text-overflow:ellipsis;font-size:12px}.planning-week-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border-top:1px solid var(--neutral-200);background:var(--neutral-50)}.planning-week-heading>span{color:var(--neutral-400);font-size:11px}.detail-query-btn{align-self:end;height:36px;min-width:80px;white-space:nowrap}
.planning-dashboard{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:1px;margin:16px 20px 16px;border:1px solid var(--neutral-200);border-radius:12px;overflow:hidden;background:var(--neutral-200)}
.planning-dashboard>div{display:flex;flex-direction:column;gap:8px;min-height:74px;padding:14px 16px;background:var(--surface)}
.planning-dashboard small{color:var(--neutral-500);font-size:12px}.planning-dashboard strong{color:var(--neutral-800);font-size:22px;line-height:1;font-variant-numeric:tabular-nums}
.detail-filter-shell{margin:0 20px 16px;padding:12px 14px;border:1px solid var(--neutral-200);border-radius:10px;background:var(--surface)}
.detail-filter-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr)) auto;gap:12px;align-items:end;margin-top:12px}.detail-filter-fields label{display:flex;flex-direction:column;gap:6px;min-width:0}.detail-filter-fields label>span{color:var(--neutral-500);font-size:12px}.detail-filter-fields input,.detail-filter-fields select{width:100%;height:36px}
.planning-account-list{display:grid;gap:8px;padding:0 20px 20px}.planning-account-card{overflow:hidden;border:1px solid var(--neutral-200);border-radius:10px;background:var(--surface);transition:border-color .14s ease,background .14s ease}.planning-account-card:hover{border-color:var(--neutral-300)}.planning-account-card.expanded{border-color:var(--primary-200)}
.planning-account-head{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:12px 14px}.planning-account-main{min-width:0;flex:1}.planning-account-identity{display:flex;flex-direction:column;gap:5px;min-width:0}.planning-account-title{display:flex;align-items:center;flex-wrap:wrap;gap:7px}.planning-account-title>strong{color:var(--neutral-900);font-size:14px;line-height:20px}.planning-account-meta{display:flex;align-items:center;flex-wrap:wrap;color:var(--neutral-400);font-size:11px;line-height:17px}.planning-account-meta span{display:inline-flex;align-items:center;min-width:0}.planning-account-meta span+span::before{display:inline-block;flex:none;width:1px;height:10px;margin:0 8px;background:var(--neutral-200);content:''}.planning-account-persona-inline{max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.planning-account-persona-inline b{margin-right:4px;color:var(--neutral-500);font-size:10px;font-weight:500}.planning-account-actions{display:flex;align-items:center;gap:8px;flex:none}.planning-plan-count{color:var(--neutral-500);font-size:11px;white-space:nowrap}.planning-expand-btn{display:inline-flex;align-items:center;gap:5px;height:30px;padding:0 9px;border:1px solid var(--neutral-200);border-radius:7px;background:var(--surface);color:var(--neutral-600);font-size:11px;cursor:pointer;transition:border-color .14s ease,background .14s ease,color .14s ease}.planning-expand-btn:hover{border-color:var(--primary-200);background:var(--primary-50);color:var(--primary-600)}.planning-expand-btn:focus-visible{outline:2px solid var(--primary-300);outline-offset:2px}.planning-expand-btn svg{transition:transform .14s ease}.planning-expand-btn svg.expanded{transform:rotate(180deg)}
.planning-week-wrap{padding:12px 14px 14px;border-top:1px solid var(--neutral-100);background:var(--neutral-50);overflow-x:auto}.planning-week-grid{display:grid;grid-template-columns:repeat(7,minmax(150px,1fr));gap:8px;min-width:1100px}.planning-day{overflow:hidden;min-height:166px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface)}.planning-day>header{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:9px 10px;border-bottom:1px solid var(--neutral-100);background:var(--neutral-50)}.planning-day>header>div{display:flex;align-items:baseline;gap:6px}.planning-day>header b{color:var(--neutral-700);font-size:12px}.planning-day>header small,.planning-day>header span{color:var(--neutral-400);font-size:10px}.planning-day-items{display:grid;gap:7px;padding:8px}.planning-plan-card{position:relative;display:flex;flex-direction:column;align-items:flex-start;gap:6px;width:100%;padding:9px;border:1px solid var(--neutral-200);border-radius:7px;background:var(--surface);color:inherit;text-align:left}.planning-plan-card.navigable{cursor:pointer;transition:border-color .14s ease,box-shadow .14s ease,transform .14s ease}.planning-plan-card.navigable:hover{border-color:var(--primary-200);box-shadow:0 4px 12px rgba(15,23,42,.05);transform:translateY(-1px)}.planning-plan-card>b{display:-webkit-box;overflow:hidden;color:var(--neutral-700);font-size:12px;line-height:18px;-webkit-line-clamp:2;-webkit-box-orient:vertical}.planning-plan-card>small{color:var(--neutral-400);font-size:10px}.planning-plan-batch{color:var(--neutral-400);font-size:9px}.planning-day-empty{display:grid;place-items:center;min-height:108px;color:var(--neutral-300);font-size:11px}
.planning-source-badge{display:inline-flex!important;align-items:center;gap:4px;border:1px solid transparent!important;font-weight:600!important}.planning-source-badge::before{width:5px;height:5px;border-radius:50%;background:currentColor;content:''}.planning-source-badge.source-ai{border-color:#bfdbfe!important;background:#eff6ff!important;color:#2563eb!important}.planning-source-badge.source-manual{border-color:#fed7aa!important;background:#fff7ed!important;color:#c2410c!important}
@media(max-width:980px){.planning-dashboard{grid-template-columns:repeat(3,minmax(0,1fr));margin:12px}.detail-filter-shell{margin:0 12px 14px}.planning-account-list{padding:0 12px 16px}.planning-account-head{align-items:flex-start;flex-direction:column;gap:10px;padding:12px}.planning-account-actions{width:100%;justify-content:flex-end}.planning-account-persona-inline{max-width:360px}}
@media(max-width:580px){.planning-dashboard{grid-template-columns:repeat(2,minmax(0,1fr))}.detail-filter-fields{grid-template-columns:minmax(0,1fr) auto}.detail-filter-fields label:first-child{grid-column:1/-1}.planning-account-meta{row-gap:2px}.planning-account-persona-inline{max-width:220px}.planning-week-wrap{padding:10px 8px 12px}.planning-account-actions{justify-content:space-between}}
</style>
