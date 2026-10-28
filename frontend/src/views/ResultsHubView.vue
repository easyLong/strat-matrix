<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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
import LegacyResultsView from './ResultsView.vue'

type ResultDimension = 'account' | 'period'
type PeriodSummary = {
  cycleStart: string
  cycleEnd: string
  batches: BatchSummary[]
  autoBatches: BatchSummary[]
  manualBatches: BatchSummary[]
  accountCount: number
  completedCount: number
  failedCount: number
  updatedAt: string | null
}

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
const failureDetails = ref<AutoFailure[]>([])
const failureLoading = ref(false)
const failureError = ref('')
const page = ref(1)
const pageSize = ref(20)
let loaded = false

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

function modeAccountCount(rows: BatchSummary[]) {
  return rows.reduce((total, batch) => total + batch.account_count, 0)
}

function summarizePeriods(source: BatchSummary[]): PeriodSummary[] {
  const grouped = new Map<string, BatchSummary[]>()
  for (const batch of source) {
    const key = cycleWeekStart(batch.cycle_start)
    const rows = grouped.get(key)
    if (rows) rows.push(batch)
    else grouped.set(key, [batch])
  }
  return [...grouped.entries()].map(([cycleStart, rows]) => {
    const ordered = [...rows].sort((a, b) => {
      if (a.plan_type !== b.plan_type) return a.plan_type === 'auto' ? -1 : 1
      return (b.updated_at || b.created_at).localeCompare(a.updated_at || a.created_at)
    })
    const autoBatches = ordered.filter(batch => batch.plan_type === 'auto')
    const manualBatches = ordered.filter(batch => batch.plan_type === 'manual')
    const updatedAt = ordered.map(batch => batch.updated_at || batch.created_at).filter(Boolean).sort((a, b) => b.localeCompare(a))[0] ?? null
    return {
      cycleStart,
      cycleEnd: cycleWeekEnd(cycleStart),
      batches: ordered,
      autoBatches,
      manualBatches,
      accountCount: modeAccountCount(ordered),
      completedCount: ordered.reduce((total, batch) => total + batch.completed_count, 0),
      failedCount: ordered.reduce((total, batch) => total + batch.failed_count, 0),
      updatedAt,
    }
  }).sort((a, b) => b.cycleStart.localeCompare(a.cycleStart))
}

function batchMatchesQuery(batch: BatchSummary, query: string) {
  const value = query.trim().toLocaleLowerCase()
  if (!value) return true
  return String(batch.id) === value || batch.batch_code.toLocaleLowerCase().includes(value)
}

const allPeriods = computed(() => summarizePeriods(batches.value))
const selectedPeriod = computed(() => allPeriods.value.find(period => period.cycleStart === requestedCycle.value) ?? null)
const selectedBatch = computed(() => batches.value.find(batch => batch.id === requestedBatchId.value) ?? null)
const searchedPeriods = computed(() => summarizePeriods(batches.value.filter(batch => batchMatchesQuery(batch, appliedFilters.value.batchQuery))))
const periods = computed(() => searchedPeriods.value.filter(period =>
  (!appliedFilters.value.startDate || period.cycleEnd >= appliedFilters.value.startDate) &&
  (!appliedFilters.value.endDate || period.cycleStart <= appliedFilters.value.endDate),
))
const pagedPeriods = computed(() => periods.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))

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

async function showFailureDetails(period: PeriodSummary) {
  failurePeriod.value = period
  failureDetails.value = []
  failureError.value = ''
  failureLoading.value = true
  try {
    const details = await api.planningFailures(period.cycleStart)
    if (failurePeriod.value?.cycleStart === period.cycleStart) failureDetails.value = details
  } catch (exc) {
    if (failurePeriod.value?.cycleStart === period.cycleStart) {
      failureError.value = exc instanceof Error ? exc.message : '读取失败详情失败'
    }
  } finally {
    if (failurePeriod.value?.cycleStart === period.cycleStart) failureLoading.value = false
  }
}

function closeFailureDetails() {
  failurePeriod.value = null
  failureDetails.value = []
  failureError.value = ''
}

function csvCell(value: unknown) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`
}

function downloadFailureUms() {
  const rows = failureDetails.value.filter(item => item.um_no)
  if (!rows.length || !failurePeriod.value) return
  const lines = [
    ['属主UM号', '账号名称', '账号ID', '批次号', '失败原因'].map(csvCell).join(','),
    ...rows.map(item => [item.um_no, item.account_name, item.account_id, item.batch_code, item.reason].map(csvCell).join(',')),
  ]
  const blob = new Blob([`\uFEFF${lines.join('\n')}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `失败账号UM号_${failurePeriod.value.cycleStart}_${failurePeriod.value.cycleEnd}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

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
  if (selectedBatch.value) void router.push({ path: '/results', query: { dimension: 'period', cycle: cycleWeekStart(selectedBatch.value.cycle_start), show_batches: '1' } })
}

async function loadBatches() {
  if (!store.databaseReady || loading.value) return
  loading.value = true
  error.value = ''
  try {
    batches.value = await api.batches(undefined, 5000)
    loaded = true
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '读取策划周期失败'
  } finally {
    loading.value = false
  }
}

watch([periods, pageSize], () => { page.value = Math.min(page.value, Math.max(1, Math.ceil(periods.value.length / pageSize.value))) })
watch([() => store.databaseReady, dimension, showingBatchDetail, showingPeriodDetail, showingAccountDetail], ([ready, currentDimension, batchDetail, periodDetail, accountDetail]) => {
  if (ready && (currentDimension === 'period' || batchDetail || periodDetail || accountDetail) && !loaded) void loadBatches()
}, { immediate: true })
</script>

<template>
  <div v-if="dimension === 'account' && !showingAccountDetail" class="account-results-shell">
    <div class="result-tabs" role="group" aria-label="策划结果查看方式">
      <button type="button" class="active" aria-pressed="true" @click="switchDimension('account')">账号列表</button>
      <button type="button" aria-pressed="false" @click="switchDimension('period')">时间列表</button>
    </div>
    <div class="legacy-account-view"><LegacyResultsView external-navigation @view-plans="openAccount" /></div>
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
      :return-label="fromManualTask ? '返回任务列表' : fromCycleDetail ? '返回周期全部批次' : '返回时间列表'"
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
                  <td><div class="period-type-stat"><b>{{ period.autoBatches.length }} 批</b><small>{{ modeAccountCount(period.autoBatches) }} 个账号</small></div></td>
                  <td><div class="period-type-stat"><b>{{ period.manualBatches.length }} 批</b><small>{{ modeAccountCount(period.manualBatches) }} 个账号</small></div></td>
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
        <ListPagination v-model:page="page" v-model:page-size="pageSize" :total="periods.length" unit="个周期" class="list-pagination-inset" />
      </section>
    </template>
  </template>

  <div v-if="failurePeriod" class="drawer-mask" @click.self="closeFailureDetails">
    <aside class="drawer failure-drawer" role="dialog" aria-modal="true" aria-labelledby="failure-detail-title">
      <div class="drawer-head">
        <div><small>失败详情</small><h2 id="failure-detail-title">{{ failurePeriod.cycleStart }} 至 {{ failurePeriod.cycleEnd }}</h2></div>
        <button class="icon-btn" type="button" aria-label="关闭失败详情" @click="closeFailureDetails">×</button>
      </div>
      <div class="drawer-body">
        <div class="failure-detail-toolbar">
          <div><b>失败账号</b><span>{{ failureDetails.length }} 个</span></div>
          <button class="btn" type="button" :disabled="failureLoading || !failureDetails.some(item => item.um_no)" @click="downloadFailureUms">导出失败 UM 号</button>
        </div>
        <p class="failure-guidance">以下账号未完成本周期策划，可转人工策划补充。</p>
        <div v-if="failureLoading" class="empty-state">正在读取失败详情…</div>
        <div v-else-if="failureError" class="banner error-banner" role="alert">{{ failureError }}</div>
        <div v-else-if="failureDetails.length === 0" class="empty-state">暂无失败账号明细</div>
        <div v-else class="table-wrap failure-table-wrap">
          <table class="failure-detail-table">
            <thead><tr><th>账号</th><th>属主 UM 号</th><th>批次</th><th>失败原因</th></tr></thead>
            <tbody><tr v-for="(item, index) in failureDetails" :key="`${item.batch_code}-${item.account_id ?? index}`">
              <td><div class="failure-account"><b>{{ item.account_name }}</b><small>{{ item.account_id || '批次级异常' }}</small></div></td>
              <td>{{ item.um_no || '—' }}</td>
              <td>{{ item.batch_code }}</td>
              <td>{{ item.reason || '未提供失败原因' }}</td>
            </tr></tbody>
          </table>
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.legacy-account-view :deep(.result-tabs){display:none}
.batch-filter-row>label{display:flex;min-width:0;flex-direction:column;gap:6px;color:var(--neutral-500);font-size:12px;font-weight:600}
.batch-filter-row>label>input{width:100%;box-sizing:border-box}
.failure-action{color:var(--danger)!important}
.failure-drawer{width:min(860px,96vw)}
.failure-detail-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 16px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--neutral-50)}
.failure-detail-toolbar>div{display:flex;align-items:baseline;gap:10px}.failure-detail-toolbar b{color:var(--neutral-800);font-size:14px}.failure-detail-toolbar span{color:var(--danger);font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}
.failure-guidance{margin:12px 0 16px;color:var(--neutral-500);font-size:13px;line-height:1.6}
.failure-table-wrap{max-height:min(560px,62vh);overflow:auto}.failure-detail-table{min-width:680px}.failure-account{display:flex;flex-direction:column;gap:3px}.failure-account b{color:var(--neutral-700);font-size:13px}.failure-account small{color:var(--neutral-400);font-size:11px}
.period-summary-row>td{vertical-align:middle}.period-type-stat{display:flex;flex-direction:column;gap:3px;white-space:nowrap}.period-type-stat b{color:var(--neutral-700);font-size:13px}.period-type-stat small{color:var(--neutral-400);font-size:11px}.period-actions{display:flex;align-items:center;gap:12px;white-space:nowrap}
.period-expansion-row>td{padding:0!important;background:var(--neutral-50)}.period-batch-panel{padding:14px 18px 18px;border-top:1px solid var(--neutral-200);border-bottom:1px solid var(--neutral-200)}.period-batch-panel>.table-wrap{margin:0;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface)}
@media(max-width:980px){.period-summary-table{min-width:980px}.period-batch-panel{padding:12px}}
</style>
