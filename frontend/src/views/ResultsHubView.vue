<script setup lang="ts">
import { computed, ref, watch,onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageBreadcrumbs from '../components/PageBreadcrumbs.vue'
import { usePageBreadcrumbs } from '../composables/usePageBreadcrumbs'
import ContentProgress from '../components/ContentProgress.vue'
import ListPagination from '../components/ListPagination.vue'
import LoadingSkeleton from '../components/LoadingSkeleton.vue'
import PlanningExport from '../components/PlanningExport.vue'
import { api } from '../api'
import { formatDateTime } from '../planningTime'
import { usePlanningStore } from '../store'
import type { AutoFailure, BatchSummary, PlanningAccountSummary } from '../types'
import { statusTone } from '../ui/status'
import PlanningDetailsView from './PlanningDetailsView.vue'
import ResultFailureDrawer from '../components/planning/ResultFailureDrawer.vue'
import AccountResultsList from '../components/AccountResultsList.vue'

type ResultDimension = 'account' | 'period'
import type { PeriodSummary } from '../api/queries'

const store = usePlanningStore()
const route = useRoute()
const router = useRouter()

const batches = ref<BatchSummary[]>([])
const loading = ref(false)
const error = ref('')
const filtersExpanded = ref(true)
const expandedPeriod = ref<string | null>(null)
const startDate = ref('')
const endDate = ref('')
const batchQuery = ref('')
const dateFilterError = ref('')
const appliedFilters = ref({ startDate: '', endDate: '', batchQuery: '' })
const failurePeriod = ref<PeriodSummary | null>(null)
usePageBreadcrumbs(() => failurePeriod.value ? [{ label: '失败详情' }] : [], { append: true, close: closeFailureDetails })
const page = ref(1)
const pageSize = ref(20)
const periodRows=ref<PeriodSummary[]>([])
const contextRows=ref<PeriodSummary[]>([])
const periodTotal=ref(0)
let loadVersion=0
let controller:AbortController|undefined

const requestedBatchId = computed(() => typeof route.query.batch === 'string' && /^\d+$/.test(route.query.batch) ? Number(route.query.batch) : null)
const requestedAccountId = computed(() => typeof route.query.account === 'string' ? route.query.account.trim() : '')
const requestedCycle = computed(() => typeof route.query.cycle === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(route.query.cycle) ? route.query.cycle : '')
const showingBatchDetail = computed(() => requestedBatchId.value !== null)
const showingAccountDetail = computed(() => !showingBatchDetail.value && Boolean(requestedAccountId.value))
const showingPeriodDetail = computed(() => !showingBatchDetail.value && !showingAccountDetail.value && Boolean(requestedCycle.value))
const dimension = computed<ResultDimension>(() => showingAccountDetail.value ? 'account' : route.query.dimension === 'period' || showingBatchDetail.value || showingPeriodDetail.value ? 'period' : 'account')
const fromManualTask = computed(() => showingBatchDetail.value && route.query.from === 'manual')
const fromCycleDetail = computed(() => showingBatchDetail.value && route.query.from === 'cycle' && Boolean(requestedCycle.value))

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

const selectedPeriod = computed(() => contextRows.value.find(period=>period.cycleStart===requestedCycle.value) ?? periodRows.value.find(period=>period.cycleStart===requestedCycle.value) ?? null)
const selectedBatch = computed(() => batches.value.find(batch=>batch.id===requestedBatchId.value) ?? null)
const periods = computed(() => periodRows.value)
const pagedPeriods = computed(() => periodRows.value)

function switchDimension(next: ResultDimension) {
  if (next === dimension.value && !showingBatchDetail.value && !showingPeriodDetail.value && !showingAccountDetail.value) return
  expandedPeriod.value = null
  void router.push({ path: '/results', query: next === 'period' ? { dimension: 'period' } : {} })
}

function applyFilters() {
  if (startDate.value && endDate.value && startDate.value > endDate.value) {
    dateFilterError.value = '开始时间不能晚于结束时间'
    return
  }
  dateFilterError.value = ''
  appliedFilters.value = { startDate: startDate.value, endDate: endDate.value, batchQuery: batchQuery.value.trim() }
  expandedPeriod.value = null
  page.value = 1
}

function showFailureDetails(period: PeriodSummary) { failurePeriod.value=period }
function closeFailureDetails() { failurePeriod.value=null }

function togglePeriod(cycleStart: string) {
  expandedPeriod.value = expandedPeriod.value === cycleStart ? null : cycleStart
}

function openPeriod(period: PeriodSummary) {
  void router.push({ path: '/results', query: { dimension: 'period', cycle: period.cycleStart } })
}

function openAccount(account: PlanningAccountSummary) {
  void router.push({ path: '/results', query: { dimension: 'account', account: account.account_id } })
}

function returnToPeriodList() {
  void router.push({ path: '/results', query: { dimension: 'period' } })
}

function openBatch(batch: BatchSummary, cycleStart?: string) {
  const query: Record<string, string> = { batch: String(batch.id), dimension: 'period' }
  if (cycleStart) query.cycle = cycleStart
  void router.push({ path: '/results', query })
}

function returnFromBatchDetail() {
  if (fromManualTask.value) void router.push('/manual')
  else if (fromCycleDetail.value) void router.push({ path: '/results', query: { dimension: 'period', cycle: requestedCycle.value, show_batches: '1' } })
  else returnToPeriodList()
}

function openBatchFromCycle(batch: BatchSummary) {
  void router.push({ path: '/results', query: { dimension: 'period', cycle: requestedCycle.value, batch: String(batch.id), from: 'cycle' } })
}

function returnToBatchCycle() {
  appliedFilters.value={...appliedFilters.value,batchQuery:''}
  if (selectedBatch.value) void router.push({ path: '/results', query: { dimension: 'period', cycle: cycleWeekStart(selectedBatch.value.cycle_start), show_batches: '1' } })
}

async function loadBatches() {
  if (!store.databaseReady) return
  const version=++loadVersion
  controller?.abort();controller=new AbortController()
  loading.value=true;error.value=''
  try {
    if (showingAccountDetail.value) { batches.value=[]; return }
    if(showingBatchDetail.value || showingPeriodDetail.value) {
      const response=await api.periodContext({mode:showingBatchDetail.value?'batch':'cycle',batch_id:requestedBatchId.value??undefined,cycle_start:requestedCycle.value||undefined,cycle_end:requestedCycle.value?cycleWeekEnd(requestedCycle.value):undefined,filters:appliedFilters.value})
      if(version!==loadVersion)return
      contextRows.value=response
      batches.value=response.flatMap(period=>period.batches)
    } else {
      const response=await api.periodPage({page:page.value,page_size:pageSize.value,filters:appliedFilters.value},controller.signal)
      if(version!==loadVersion)return
      periodRows.value=response.items;periodTotal.value=response.total
      const max=Math.max(1,Math.ceil(response.total/pageSize.value));if(page.value>max)page.value=max
    }
  } catch(exc) { if(version===loadVersion)error.value=exc instanceof Error?exc.message:'读取策划结果失败' }
  finally {if(version===loadVersion)loading.value=false}
}
watch([()=>store.databaseReady,dimension,requestedBatchId,requestedCycle,requestedAccountId],()=>{if(store.databaseReady&&(dimension.value==='period'||showingAccountDetail.value))void loadBatches()},{immediate:true})
watch([page,pageSize,appliedFilters],()=>{if(store.databaseReady&&dimension.value==='period'&&!showingBatchDetail.value&&!showingPeriodDetail.value)void loadBatches()})
onBeforeUnmount(()=>{++loadVersion;controller?.abort()})
</script>

<template>
  <div v-if="dimension === 'account' && !showingAccountDetail" class="account-results-shell">
    <div class="result-tabs" role="group" aria-label="策划结果查看方式">
      <button type="button" class="active" aria-pressed="true" @click="switchDimension('account')">账号列表</button>
      <button type="button" aria-pressed="false" @click="switchDimension('period')">时间列表</button>
    </div>
    <div class="legacy-account-view"><AccountResultsList @view-plans="openAccount" /></div>
  </div>

  <template v-else>
    <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
    <section v-if="loading || !store.initialized" class="card"><LoadingSkeleton /></section>

    <PlanningDetailsView
      v-else-if="showingAccountDetail"
      mode="account"
      :account-id="requestedAccountId"
      :cycle-start="requestedCycle"
      cycle-end=""
      :batches="batches"
      @back="switchDimension('account')"
    />

    <PlanningDetailsView
      v-else-if="showingBatchDetail && selectedBatch"
      mode="batch"
      :cycle-start="cycleWeekStart(selectedBatch.cycle_start)"
      :cycle-end="cycleWeekEnd(selectedBatch.cycle_start)"
      :batches="[selectedBatch]"
      :return-label="fromManualTask ? '返回任务列表' : fromCycleDetail ? '查看所有批次' : '返回时间列表'"
      :show-cycle-link="!fromCycleDetail"
      @back="returnFromBatchDetail"
      @view-cycle="returnToBatchCycle"
    />
    <section v-else-if="showingBatchDetail" class="card"><div class="empty-state"><b>未找到该批次</b></div></section>

    <PlanningDetailsView
      v-else-if="showingPeriodDetail && selectedPeriod"
      mode="cycle"
      :cycle-start="selectedPeriod.cycleStart"
      :cycle-end="selectedPeriod.cycleEnd"
      :batches="selectedPeriod.batches"
      :initial-batches-expanded="route.query.show_batches === '1'"
      @back="returnToPeriodList"
      @open-batch="openBatchFromCycle"
    />
    <section v-else-if="showingPeriodDetail" class="card"><div class="empty-state"><b>未找到该策划周期</b></div></section>

    <template v-else>
      <div class="result-tabs" role="group" aria-label="策划结果查看方式">
        <button type="button" aria-pressed="false" @click="switchDimension('account')">账号列表</button>
        <button type="button" class="active" aria-pressed="true" @click="switchDimension('period')">时间列表</button>
      </div>

      <section class="card period-result-card">
        <div class="card-body batch-dimension-filters">
          <button class="filter-collapse-toggle" type="button" aria-controls="period-dimension-filter-fields" :aria-expanded="filtersExpanded" @click="filtersExpanded = !filtersExpanded">
            <span>筛选条件</span>
            <svg :class="{ expanded: filtersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg>
          </button>
          <div id="period-dimension-filter-fields" v-show="filtersExpanded" class="batch-filter-fields">
            <div class="batch-filter-row query-filter-grid" data-query-filters="standard">
              <label><span>开始时间</span><input v-model="startDate" type="date" :max="endDate || undefined" aria-label="开始时间" @keydown.enter.prevent="applyFilters" /></label>
              <label><span>结束时间</span><input v-model="endDate" type="date" :min="startDate || undefined" aria-label="结束时间" @keydown.enter.prevent="applyFilters" /></label>
              <label><span>批次号或批次 ID</span><input v-model="batchQuery" type="search" aria-label="批次号或批次 ID" placeholder="输入批次号或批次 ID" @keydown.enter.prevent="applyFilters" /></label>
              <div class="query-filter-actions"><button class="btn primary" type="button" @click="applyFilters">查询</button></div>
            </div>
            <p v-if="dateFilterError" class="inline-error" role="alert">{{ dateFilterError }}</p>
          </div>
        </div>

        <div class="table-wrap">
          <table class="period-summary-table">
            <thead><tr><th>策划周期</th><th>批次构成</th><th>AI 自动策划</th><th>人工策划</th><th>账号数</th><th>完成数</th><th>失败数</th><th>最后更新</th><th>操作</th></tr></thead>
            <tbody>
              <template v-for="period in pagedPeriods" :key="period.cycleStart">
                <tr class="period-summary-row">
                  <td><div class="account-name-cell"><b>{{ period.cycleStart }} 至 {{ period.cycleEnd }}</b></div></td>
                  <td><span class="tag blue">{{ period.batches.length }} 个批次</span></td>
                  <td><div class="period-type-stat"><b>{{ period.autoBatches.length }} 批</b><small>{{ period.autoAccountCount }} 个账号</small></div></td>
                  <td><div class="period-type-stat"><b>{{ period.manualBatches.length }} 批</b><small>{{ period.manualAccountCount }} 个账号</small></div></td>
                  <td><b>{{ period.accountCount }}</b></td>
                  <td class="batch-count" :class="{ completed: period.completedCount > 0 }">{{ period.completedCount }}</td>
                  <td class="batch-count" :class="{ failed: period.failedCount > 0 }">{{ period.failedCount }}</td>
                  <td>{{ formatDateTime(period.updatedAt) }}</td>
                  <td><div class="period-actions">
                    <button class="text-btn" type="button" :aria-expanded="expandedPeriod === period.cycleStart" @click="togglePeriod(period.cycleStart)">{{ expandedPeriod === period.cycleStart ? '收起批次' : '查看批次' }}</button>
                    <button class="text-btn" type="button" @click="openPeriod(period)">查看策划</button>
                    <PlanningExport inline :batches="period.batches" :filename="`策划明细_${period.cycleStart}_${period.cycleEnd}.csv`" />
                    <button v-if="period.failedCount > 0" class="text-btn failure-action" type="button" @click="showFailureDetails(period)">查看失败详情</button>
                  </div></td>
                </tr>
                <tr v-if="expandedPeriod === period.cycleStart" class="period-expansion-row">
                  <td colspan="9">
                    <div class="period-batch-panel"><div class="table-wrap"><table>
                      <thead><tr><th>批次</th><th>策划方式</th><th>批次周期</th><th>账号数</th><th>完成数</th><th>失败数</th><th>选题数</th><th>策划状态</th><th title="完成内容生产的账号数 / 总账号数">内容进度</th><th>更新时间</th><th>操作</th></tr></thead>
                      <tbody><tr v-for="batch in period.batches" :key="batch.id">
                        <td><div class="account-name-cell"><b>{{ batch.task_name || '—' }}</b><small>ID {{ batch.batch_code }}</small></div></td>
                        <td>{{ batch.plan_type === 'manual' ? '人工策划' : 'AI 自动策划' }}</td>
                        <td>{{ batch.cycle_start }} 至 {{ batch.cycle_end }}</td>
                        <td>{{ batch.account_count }}</td>
                        <td class="batch-count" :class="{ completed: batch.completed_count > 0 }">{{ batch.completed_count }}</td>
                        <td class="batch-count" :class="{ failed: batch.failed_count > 0 }">{{ batch.failed_count }}</td>
                        <td>{{ batch.topic_count }}</td>
                        <td><span :class="['tag', statusTone(batch.planning_status)]">{{ batch.planning_status || batch.status }}</span></td>
                        <td><ContentProgress display="status" :completed="batch.content_completed_account_count" :total="batch.account_count" /></td>
                        <td>{{ formatDateTime(batch.updated_at || batch.created_at) }}</td>
                        <td><div class="period-actions"><button class="text-btn" type="button" @click="openBatch(batch, period.cycleStart)">查看策划</button><PlanningExport inline :batches="[batch]" :filename="`策划明细_${batch.batch_code}.csv`" /></div></td>
                      </tr></tbody>
                    </table></div></div>
                  </td>
                </tr>
              </template>
              <tr v-if="periods.length === 0"><td colspan="9"><div class="empty-state"><b>暂无符合条件的策划周期</b></div></td></tr>
            </tbody>
          </table>
        </div>
        <ListPagination v-model:page="page" v-model:page-size="pageSize" :total="periodTotal" unit="个周期" class="list-pagination-inset" />
      </section>
    </template>
  </template>

  <ResultFailureDrawer v-if="failurePeriod" :failure-period="failurePeriod" @close="closeFailureDetails" />
</template>

<style scoped>
.legacy-account-view :deep(.result-tabs){display:none}
.batch-filter-row>label{display:flex;min-width:0;flex-direction:column;gap:6px;color:var(--neutral-500);font-size:12px;font-weight:600}
.batch-filter-row>label>input{width:100%;box-sizing:border-box}
.failure-action{color:var(--danger)!important}
.period-summary-row>td{vertical-align:middle}.period-type-stat{display:flex;flex-direction:column;gap:3px;white-space:nowrap}.period-type-stat b{color:var(--neutral-700);font-size:13px}.period-type-stat small{color:var(--neutral-400);font-size:11px}.period-actions{display:flex;align-items:center;gap:12px;white-space:nowrap}
.period-expansion-row>td{padding:0!important;background:var(--neutral-50)}.period-batch-panel{padding:14px 18px 18px;border-top:1px solid var(--neutral-200);border-bottom:1px solid var(--neutral-200)}.period-batch-panel>.table-wrap{margin:0;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface)}
@media(max-width:980px){.period-summary-table{min-width:980px}.period-batch-panel{padding:12px}}
</style>
