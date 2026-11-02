<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import AccountTypeBadge from '../components/AccountTypeBadge.vue'
import LoadingSkeleton from '../components/LoadingSkeleton.vue'
import ListPagination from '../components/ListPagination.vue'
import HoverHint from '../components/HoverHint.vue'
import PlanningResultStats from '../components/planning/PlanningResultStats.vue'
import PlanningWeekCalendar from '../components/planning/PlanningWeekCalendar.vue'
import { weekStart,weekEnd,cyclePeriodLabel,type PlanningWeek } from '../ui/planningCalendar'
import PlanDetailDrawer from '../components/planning/PlanDetailDrawer.vue'
import { api } from '../api'
import type { AccountOption, AccountPlanRecord, BatchSummary } from '../types'
import { statusTone } from '../ui/status'
import { productionStatusLabel } from '../ui/slotContentStatus'
import type { ContentTypeCount } from '../ui/contentTypeStats'
import { formatDateTime } from '../planningTime'

type DetailMode = 'batch' | 'cycle' | 'account'

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
  initialBatchesExpanded?: boolean
  showCycleLink?: boolean
}>(), { mode: 'cycle', accountId: '', returnLabel: '', initialBatchesExpanded: false, showCycleLink: false })

const emit = defineEmits<{
  back: []
  openBatch: [batch: BatchSummary]
  viewCycle: []
}>()

const loading = ref(false)
const error = ref('')
const pageItems = ref<AccountPlanRecord[]>([])
const resultTotal = ref(0)
const resultSummary = ref({ accounts: 0, batches: 0, topics: 0 })
const resultDistribution = ref<ContentTypeCount[]>([])
const resultContentTypes = ref<string[]>([])
const accountCatalog = ref<AccountOption[]>([])
const expandedAccounts = ref(new Set<string>())
const filtersExpanded = ref(true)
const batchesExpanded = ref(props.initialBatchesExpanded)
const batchPage = ref(1)
const batchPageSize = ref(10)
const pagedCycleBatches = computed(() => props.batches.slice((batchPage.value - 1) * batchPageSize.value, batchPage.value * batchPageSize.value))
const accountKeyword = ref('')
const contentType = ref('all')
const selectedPlan = ref<AccountPlanRecord | null>(null)
const dateStart = ref('')
const dateEnd = ref('')
const dateFilterError = ref('')
const appliedFilters = ref({ account: '', start: '', end: '', batch: 'all', planType: 'all', contentType: 'all' })
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
watch(() => [props.mode, props.accountId, props.cycleStart, props.batches.map(batch => batch.id).join(',')], () => {
  selectedPlan.value = null
})
const productionItems = computed(() => pageItems.value)
const backLabel = computed(() => props.returnLabel || (isAccountMode.value ? '返回账号列表' : '返回时间列表'))
const fixedPlanType = computed<'auto' | 'manual' | null>(() => isBatchMode.value ? currentBatch.value?.plan_type ?? null : null)
const scopeLabel = computed(() => {
  if (isAccountMode.value) return `${accountProfile(props.accountId)?.account_name || pageItems.value[0]?.account_name || props.accountId} · ${props.accountId}`
  if (currentBatch.value) return [currentBatch.value.task_name, currentBatch.value.batch_code].filter(Boolean).join(' · ')
  return cyclePeriodLabel(props.cycleStart)
})
const scopePlanType = computed(() => {
  return fixedPlanType.value === 'manual' ? '人工策划' : 'AI 自动策划'
})

function accountProfile(accountId: string) {
  return accountCatalog.value.find(account => account.account_id === accountId)
}

function accountTypeLabel(profile?: AccountOption) {
  return profile?.account_type || (profile?.certified === true ? '认证' : profile?.certified === false ? '非认证' : '—')
}

const contentTypes = computed(() => resultContentTypes.value)
const filteredItems = computed(() => pageItems.value)

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
})

const pagedAccountGroups = computed(() => accountGroups.value)
const accountWeeks = computed(() => accountGroups.value.length ? weeksFor(accountGroups.value[0]!) : [])
const pagedAccountWeeks = computed(() => accountWeeks.value)

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

function toggleAccount(accountId: string) {
  const next = new Set(expandedAccounts.value)
  if (next.has(accountId)) next.delete(accountId)
  else next.add(accountId)
  expandedAccounts.value = next
}

function updatePlan(item: AccountPlanRecord) {
  pageItems.value = pageItems.value.map(record => record.id === item.id ? { ...record, ...item } : record)
  void load(true)
}

let detailRequest: AbortController | undefined
async function load(silent = false) {
  const request = ++loadRequest
  detailRequest?.abort()
  detailRequest = new AbortController()
  if (!silent) loading.value = true
  error.value = ''
  try {
    const response = await api.planPage({
      mode: props.mode,
      batch_ids: props.mode === 'cycle' ? props.batches.map(batch=>batch.id) : undefined,
      account_id: isAccountMode.value ? props.accountId : undefined,
      batch_id: isBatchMode.value ? currentBatch.value?.id : undefined,
      cycle_start: props.mode === 'cycle' ? props.cycleStart : undefined,
      cycle_end: props.mode === 'cycle' ? props.cycleEnd : undefined,
      page: isAccountMode.value ? historyPage.value : page.value,
      page_size: isAccountMode.value ? historyPageSize.value : pageSize.value,
      filters: appliedFilters.value,
    }, detailRequest.signal)
    if (request !== loadRequest) return
    const currentPage = isAccountMode.value ? historyPage : page
    const currentSize = isAccountMode.value ? historyPageSize.value : pageSize.value
    const maximum = Math.max(1, Math.ceil(response.total / currentSize))
    if (currentPage.value > maximum) { currentPage.value = maximum; return }
    pageItems.value = response.items
    resultTotal.value = response.total
    resultSummary.value = response.summary
    resultDistribution.value = response.distribution
    resultContentTypes.value = response.content_types
    accountCatalog.value = response.accounts
    if (isAccountMode.value) expandedAccounts.value = new Set([props.accountId])
  } catch (exc) {
    if (request === loadRequest) error.value = exc instanceof Error ? exc.message : '读取策划明细失败'
  } finally {
    if (request === loadRequest) loading.value = false
  }
}

function applyFilters() {
  if (isAccountMode.value && dateStart.value && dateEnd.value && dateStart.value > dateEnd.value) {
    dateFilterError.value = '开始日期不能晚于结束日期'
    return
  }
  dateFilterError.value = ''
  appliedFilters.value = {
    account: isAccountMode.value ? '' : accountKeyword.value,
    start: isAccountMode.value ? dateStart.value : '',
    end: isAccountMode.value ? dateEnd.value : '',
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
  dateStart.value = isAccountMode.value ? props.cycleStart : ''
  dateEnd.value = isAccountMode.value && props.cycleStart ? weekEnd(props.cycleStart) : ''
  dateFilterError.value = ''
  filtersExpanded.value = true
  applyFilters()
  expandedAccounts.value = new Set()
  selectedPlan.value = null
  void load()
}, { immediate: true })
watch(pageSize, () => { page.value = 1 })
watch([page, pageSize, historyPage, historyPageSize, appliedFilters], () => { void load() })
watch(historyPageSize, () => { historyPage.value = 1 })
const productionTimer = window.setInterval(() => {
  if (!loading.value && productionItems.value.some(item => item.topic_id && ['待生产', '生产中'].includes(productionStatusLabel(item)))) void load(true)
}, 3000)
onBeforeUnmount(() => { loadRequest++; detailRequest?.abort(); window.clearInterval(productionTimer) })
</script>

<template>
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
          <HoverHint text="投放日期" :show-icon="false" class="tag gray planning-context-tag">{{ appliedFilters.start || appliedFilters.end ? `${appliedFilters.start || '不限'} 至 ${appliedFilters.end || '不限'}` : '全部日期' }}</HoverHint>
        </div>
        <div v-else class="planning-detail-scope"><HoverHint text="周期" :show-icon="false" class="tag gray planning-context-tag">{{ scopeLabel }}</HoverHint></div>
      </div>
      <div class="planning-detail-actions">
        <button v-if="isBatchMode && showCycleLink" class="btn" type="button" @click="emit('viewCycle')">查看所有批次</button>
        <button class="btn" type="button" @click="emit('back')">{{ backLabel }}</button>
      </div>
    </div>

    <LoadingSkeleton v-if="loading" :rows="8" />
    <div v-else-if="error" class="banner error-banner" role="alert">{{ error }}</div>
    <template v-else>
      <div class="detail-filter-shell">
        <button class="filter-collapse-toggle" type="button" :aria-expanded="filtersExpanded" @click="filtersExpanded = !filtersExpanded">
          <span>筛选条件</span>
          <svg :class="{ expanded: filtersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg>
        </button>
        <div v-show="filtersExpanded" class="detail-filter-fields query-filter-grid" data-query-filters="compact">
          <label v-if="!isAccountMode"><span>账号 ID 或昵称</span><input v-model="accountKeyword" type="search" placeholder="输入账号 ID 或昵称" /></label>
          <label v-if="isAccountMode"><span>开始日期</span><input v-model="dateStart" type="date" :max="dateEnd || undefined" /></label>
          <label v-if="isAccountMode"><span>结束日期</span><input v-model="dateEnd" type="date" :min="dateStart || undefined" /></label>
          <div class="query-filter-tail">
            <label><span>选题二级分类</span><select v-model="contentType"><option value="all">全部选题二级分类</option><option v-for="value in contentTypes" :key="value" :value="value">{{ value }}</option></select></label>
            <div class="query-filter-actions"><button class="btn primary detail-query-btn" type="button" @click="applyFilters">查询</button></div>
          </div>
        </div>
        <p v-if="dateFilterError" class="inline-error" role="alert">{{ dateFilterError }}</p>
      </div>

      <PlanningResultStats :mode="mode" :summary="resultSummary" :distribution="resultDistribution">
      <div v-if="!isBatchMode && !isAccountMode" class="cycle-batch-action">
        <button class="text-btn cycle-batch-toggle" type="button" :aria-expanded="batchesExpanded" aria-controls="cycle-batch-list" @click="batchesExpanded = !batchesExpanded">{{ batchesExpanded ? '收起批次' : '查看批次' }}</button>
      </div>

      <section v-if="!isBatchMode && !isAccountMode && batchesExpanded" id="cycle-batch-list" class="cycle-batch-list">
        <div class="cycle-batch-title"><b>本周期批次</b><span>{{ batches.length }} 个批次</span></div>
        <div class="table-wrap"><table><thead><tr><th>批次</th><th>策划方式</th><th>账号数</th><th>策划状态</th><th>更新时间</th><th>操作</th></tr></thead>
          <tbody><tr v-for="batch in pagedCycleBatches" :key="batch.id"><td><div class="cycle-batch-identity"><b>{{ batch.task_name || '—' }}</b><small>{{ batch.batch_code }}</small></div></td><td>{{ batch.plan_type === 'manual' ? '人工策划' : '自动策划' }}</td><td>{{ batch.account_count }}</td><td>{{ batch.planning_status || batch.status }}</td><td>{{ formatDateTime(batch.updated_at || batch.created_at) }}</td><td><button class="text-btn" type="button" @click="emit('openBatch', batch)">查看策划</button></td></tr><tr v-if="!batches.length"><td colspan="6" class="empty-state">暂无批次</td></tr></tbody>
        </table></div>
        <ListPagination v-if="batches.length > 10" v-model:page="batchPage" v-model:page-size="batchPageSize" :total="batches.length" unit="个批次" />
      </section>

      </PlanningResultStats>

      <template v-if="isAccountMode">
        <div v-if="accountGroups.length" class="planning-account-list">
          <div v-for="week in pagedAccountWeeks" :key="week.start" class="planning-week-section">
            <div class="planning-week-heading"><span>{{ cyclePeriodLabel(week.start) }} · {{ week.start }} 至 {{ week.end }}</span><span>{{ week.items.length }} 条策划</span></div>
            <PlanningWeekCalendar :week="week" @select="selectedPlan = $event" />
          </div>
        </div>
        <div v-else class="empty-state">暂无策划记录</div>
        <ListPagination v-if="resultTotal" v-model:page="historyPage" v-model:page-size="historyPageSize" :total="resultTotal" unit="周" class="list-pagination-inset" />
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
                  <span>账号 ID：{{ group.account_id || '—' }}</span>
                  <span>属主 UM 号：{{ group.profile?.um_no || '—' }}</span>
                  <span>所属组织：{{ group.profile?.organization || '—' }}</span>
                  <span>平台：{{ group.profile?.platform || '—' }}</span>
                  <span class="planning-account-persona-inline" :title="group.profile?.persona || '未配置'">人设：{{ group.profile?.persona || '未配置' }}</span>
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
          <PlanningWeekCalendar :week="week" compact-source :show-batch="!isBatchMode" show-topic-type @select="selectedPlan = $event" />
          </div>
          </template>
        </article>
      </div>
      <div v-else class="empty-state"><b>当前筛选条件下暂无策划结果</b></div>
      <ListPagination v-if="!isAccountMode && resultTotal" v-model:page="page" v-model:page-size="pageSize" :total="resultTotal" unit="个账号" class="list-pagination-inset" />
    </template>
  </section>
  <PlanDetailDrawer v-if="selectedPlan" :plan="selectedPlan" @close-plan="selectedPlan = null" @plan-updated="updatePlan" />
</template>

<style scoped>
.cycle-batch-toggle{margin-top:3px;align-self:flex-start;font-size:12px}.cycle-batch-list{margin:0 20px 16px;border:1px solid var(--neutral-200);border-radius:8px;overflow:hidden}.cycle-batch-title{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:var(--neutral-50);font-size:13px}.cycle-batch-title span,.cycle-batch-identity small{color:var(--neutral-500);font-size:12px}.cycle-batch-identity{display:flex;flex-direction:column;gap:3px}.cycle-batch-list table{min-width:720px}
.cycle-batch-action{display:flex;justify-content:flex-end;margin:-8px 20px 12px}
.account-plan-table-wrap{margin:0 20px 20px}.account-plan-table{table-layout:fixed;min-width:1180px}.account-plan-table th,.account-plan-table td{padding:14px 12px;vertical-align:top;line-height:22px}.account-plan-table td{color:var(--neutral-700)}.account-plan-date{white-space:nowrap;font-variant-numeric:tabular-nums}.account-plan-text{white-space:pre-wrap;overflow-wrap:anywhere}.account-plan-batch{overflow-wrap:anywhere}.account-plan-batch>span{display:block}.account-plan-batch>small{margin-top:3px;font-size:12px;line-height:18px}.account-plan-table .empty-state{text-align:center;padding:32px 12px;color:var(--neutral-400)}
@media(max-width:980px){.account-plan-table-wrap{margin:0 12px 16px}}
.planning-detail-head{align-items:flex-start;flex-wrap:wrap}.planning-detail-heading{flex:1 1 260px;min-width:0}.planning-detail-actions{display:flex;flex:0 0 auto;align-items:center;align-self:flex-start;justify-content:flex-end;flex-wrap:wrap;gap:8px;max-width:100%;margin-left:auto}.planning-detail-actions .btn{white-space:nowrap}.planning-detail-scope .planning-context-tag{min-width:0;max-width:100%;min-height:24px;padding:3px 8px;border-radius:6px;background:var(--neutral-100);color:var(--neutral-500);font-size:12px;line-height:18px;font-weight:500}.planning-batch-code{min-width:0;max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.planning-batch-scope .planning-context-tag.orange{background:var(--processing-bg);color:var(--processing)}.planning-batch-scope .planning-context-tag.blue{background:var(--primary-50);color:var(--primary-600)}
.planning-detail-scope{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-top:6px;min-width:0}.planning-scope-label{max-width:560px;overflow:hidden;text-overflow:ellipsis;font-size:12px}.planning-week-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border-top:1px solid var(--neutral-200);background:var(--neutral-50)}.planning-week-heading>span{color:var(--neutral-400);font-size:11px}.detail-query-btn{align-self:end;height:36px;min-width:80px;white-space:nowrap}
.detail-filter-shell{margin:0 20px 16px;padding:12px 14px;border:1px solid var(--neutral-200);border-radius:10px;background:var(--surface)}
.planning-detail-card>.detail-filter-shell{margin-top:16px;margin-bottom:0}
.detail-filter-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr)) auto;gap:12px;align-items:end;margin-top:12px}.detail-filter-fields label{display:flex;flex-direction:column;gap:6px;min-width:0}.detail-filter-fields label>span{color:var(--neutral-500);font-size:12px}.detail-filter-fields input,.detail-filter-fields select{width:100%;height:36px}
.planning-account-list{display:grid;gap:8px;padding:0 20px 20px}.planning-account-card{overflow:hidden;border:1px solid var(--neutral-200);border-radius:10px;background:var(--surface);transition:border-color .14s ease,background .14s ease}.planning-account-card:hover{border-color:var(--neutral-300)}.planning-account-card.expanded{border-color:var(--primary-200)}
.planning-account-head{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:12px 14px}.planning-account-main{min-width:0;flex:1}.planning-account-identity{display:flex;flex-direction:column;gap:5px;min-width:0}.planning-account-title{display:flex;align-items:center;flex-wrap:wrap;gap:7px}.planning-account-title>strong{color:var(--neutral-900);font-size:14px;line-height:20px}.planning-account-meta{display:flex;align-items:center;flex-wrap:wrap;color:var(--neutral-400);font-size:11px;line-height:17px}.planning-account-meta span{display:inline-flex;align-items:center;min-width:0}.planning-account-meta span+span::before{display:inline-block;flex:none;width:1px;height:10px;margin:0 8px;background:var(--neutral-200);content:''}.planning-account-persona-inline{max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.planning-account-persona-inline b{margin-right:4px;color:var(--neutral-500);font-size:10px;font-weight:500}.planning-account-actions{display:flex;align-items:center;gap:8px;flex:none}.planning-plan-count{color:var(--neutral-500);font-size:11px;white-space:nowrap}.planning-expand-btn{display:inline-flex;align-items:center;gap:5px;height:30px;padding:0 9px;border:1px solid var(--neutral-200);border-radius:7px;background:var(--surface);color:var(--neutral-600);font-size:11px;cursor:pointer;transition:border-color .14s ease,background .14s ease,color .14s ease}.planning-expand-btn:hover{border-color:var(--primary-200);background:var(--primary-50);color:var(--primary-600)}.planning-expand-btn:focus-visible{outline:2px solid var(--primary-300);outline-offset:2px}.planning-expand-btn svg{transition:transform .14s ease}.planning-expand-btn svg.expanded{transform:rotate(180deg)}
@media(max-width:980px){.detail-filter-shell{margin:0 12px 14px}.planning-account-list{padding:0 12px 16px}.planning-account-head{align-items:flex-start;flex-direction:column;gap:10px;padding:12px}.planning-account-actions{width:100%;justify-content:flex-end}.planning-account-persona-inline{max-width:360px}}
@media(max-width:580px){.detail-filter-fields{grid-template-columns:minmax(0,1fr) auto}.detail-filter-fields label:first-child{grid-column:1/-1}.planning-account-meta{row-gap:2px}.planning-account-persona-inline{max-width:220px}.planning-account-actions{justify-content:space-between}}
</style>
