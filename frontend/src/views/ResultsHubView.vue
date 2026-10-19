<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ContentProgress from '../components/ContentProgress.vue'
import ListPagination from '../components/ListPagination.vue'
import LoadingSkeleton from '../components/LoadingSkeleton.vue'
import { api } from '../api'
import { formatDateTime } from '../planningTime'
import { usePlanningStore } from '../store'
import type { BatchSummary } from '../types'
import { statusTone } from '../ui/status'
import CycleDetailView from './CycleDetailView.vue'
import LegacyResultsView from './ResultsView.vue'

type ResultDimension = 'account' | 'period'

type PeriodSummary = {
  cycleStart: string
  cycleEnd: string
  batches: BatchSummary[]
  autoBatches: BatchSummary[]
  manualBatches: BatchSummary[]
  planningCount: number
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
const filtersExpanded = ref(false)
const expandedPeriod = ref<string | null>(null)
const year = ref('all')
const month = ref('all')
const week = ref('all')
const appliedFilters = ref({ year: 'all', month: 'all', week: 'all' })
const page = ref(1)
const pageSize = ref(20)
let loaded = false

const showingBatchDetail = computed(() => typeof route.query.batch === 'string' && /^\d+$/.test(route.query.batch))
const dimension = computed<ResultDimension>(() => route.query.dimension === 'period' ? 'period' : 'account')
const requestedCycle = computed(() => typeof route.query.cycle === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(route.query.cycle) ? route.query.cycle : '')
const showingPeriodDetail = computed(() => dimension.value === 'period' && !showingBatchDetail.value && Boolean(requestedCycle.value))

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

function monthWeekOf(date: string) {
  const monday = new Date(`${cycleWeekStart(date)}T00:00:00Z`)
  return Math.floor((monday.getUTCDate() - 1) / 7) + 1
}

function cyclePeriodLabel(date: string) {
  const monday = new Date(`${cycleWeekStart(date)}T00:00:00Z`)
  return `${monday.getUTCFullYear()}年${monday.getUTCMonth() + 1}月第${monthWeekOf(date)}周`
}

function batchPlanningCount(batch: BatchSummary) {
  return batch.content_count || batch.result_count || batch.completed_count + batch.failed_count
}

function modePlanningCount(rows: BatchSummary[]) {
  return rows.reduce((total, batch) => total + batchPlanningCount(batch), 0)
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
    const updatedAt = ordered
      .map(batch => batch.updated_at || batch.created_at)
      .filter(Boolean)
      .sort((a, b) => b.localeCompare(a))[0] ?? null
    return {
      cycleStart,
      cycleEnd: cycleWeekEnd(cycleStart),
      batches: ordered,
      autoBatches,
      manualBatches,
      planningCount: modePlanningCount(ordered),
      completedCount: ordered.reduce((total, batch) => total + batch.completed_count, 0),
      failedCount: ordered.reduce((total, batch) => total + batch.failed_count, 0),
      updatedAt,
    }
  }).sort((a, b) => b.cycleStart.localeCompare(a.cycleStart))
}

const allPeriods = computed(() => summarizePeriods(batches.value))
const periodKeys = computed(() => allPeriods.value.map(period => period.cycleStart))
const yearOptions = computed(() => [...new Set(periodKeys.value.map(value => value.slice(0, 4)))].sort((a, b) => b.localeCompare(a)))
const monthOptions = computed(() => [...new Set(periodKeys.value
  .filter(value => year.value === 'all' || value.slice(0, 4) === year.value)
  .map(value => value.slice(5, 7)))].sort())
const weekOptions = computed(() => [...new Set(periodKeys.value
  .filter(value => (year.value === 'all' || value.slice(0, 4) === year.value) && (month.value === 'all' || value.slice(5, 7) === month.value))
  .map(value => monthWeekOf(value)))].sort((a, b) => a - b))

const periods = computed(() => allPeriods.value.filter(period =>
  (appliedFilters.value.year === 'all' || period.cycleStart.slice(0, 4) === appliedFilters.value.year) &&
  (appliedFilters.value.month === 'all' || period.cycleStart.slice(5, 7) === appliedFilters.value.month) &&
  (appliedFilters.value.week === 'all' || String(monthWeekOf(period.cycleStart)) === appliedFilters.value.week),
))

const pagedPeriods = computed(() => periods.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const selectedPeriod = computed(() => allPeriods.value.find(period => period.cycleStart === requestedCycle.value) ?? null)

function switchDimension(next: ResultDimension) {
  if (next === dimension.value && !showingBatchDetail.value && !showingPeriodDetail.value) return
  expandedPeriod.value = null
  void router.push({ path: '/results', query: next === 'period' ? { dimension: 'period' } : {} })
}

function applyFilters() {
  appliedFilters.value = { year: year.value, month: month.value, week: week.value }
  expandedPeriod.value = null
  page.value = 1
}

function togglePeriod(cycleStart: string) {
  expandedPeriod.value = expandedPeriod.value === cycleStart ? null : cycleStart
}

function openPeriod(period: PeriodSummary) {
  void router.push({ path: '/results', query: { dimension: 'period', cycle: period.cycleStart } })
}

function returnToPeriodList() {
  void router.push({ path: '/results', query: { dimension: 'period' } })
}

function openBatch(batch: BatchSummary, cycleStart?: string) {
  const query: Record<string, string> = { batch: String(batch.id), dimension: 'period' }
  if (cycleStart) query.cycle = cycleStart
  void router.push({ path: '/results', query })
}

function interceptBatchBack(event: Event) {
  const target = event.target instanceof Element ? event.target.closest('button') : null
  if (!target || !target.textContent?.includes('返回批次维度')) return
  event.preventDefault()
  event.stopPropagation()
  if (requestedCycle.value) {
    void router.push({ path: '/results', query: { dimension: 'period', cycle: requestedCycle.value } })
  } else {
    returnToPeriodList()
  }
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

watch(year, () => { month.value = 'all'; week.value = 'all' })
watch(month, () => { week.value = 'all' })
watch([periods, pageSize], () => { page.value = Math.min(page.value, Math.max(1, Math.ceil(periods.value.length / pageSize.value))) })
watch([() => store.databaseReady, dimension], ([ready, currentDimension]) => {
  if (ready && currentDimension === 'period' && !loaded) void loadBatches()
}, { immediate: true })
</script>

<template>
  <div v-if="showingBatchDetail" class="legacy-batch-detail" @click.capture="interceptBatchBack">
    <LegacyResultsView />
  </div>

  <template v-else>
    <div v-if="!showingPeriodDetail" class="result-tabs" role="group" aria-label="策划结果查看维度">
      <button type="button" :class="{ active: dimension === 'account' }" :aria-pressed="dimension === 'account'" @click="switchDimension('account')">账号维度</button>
      <button type="button" :class="{ active: dimension === 'period' }" :aria-pressed="dimension === 'period'" @click="switchDimension('period')">周期维度</button>
    </div>

    <div v-if="dimension === 'account'" class="legacy-account-view">
      <LegacyResultsView />
    </div>

    <template v-else>
      <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
      <section v-if="loading || !store.initialized" class="card"><LoadingSkeleton /></section>

      <CycleDetailView
        v-else-if="showingPeriodDetail && selectedPeriod"
        :cycle-start="selectedPeriod.cycleStart"
        :cycle-end="selectedPeriod.cycleEnd"
        :batches="selectedPeriod.batches"
        @back="returnToPeriodList"
        @open-batch="batch => openBatch(batch, selectedPeriod?.cycleStart)"
      />
      <section v-else-if="showingPeriodDetail" class="card"><div class="empty-state"><b>未找到该策划周期</b></div></section>

      <section v-else class="card period-result-card">
        <div class="card-body batch-dimension-filters">
          <button class="filter-collapse-toggle" type="button" aria-controls="period-dimension-filter-fields" :aria-expanded="filtersExpanded" @click="filtersExpanded = !filtersExpanded">
            <span>筛选条件</span>
            <svg :class="{ expanded: filtersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg>
          </button>
          <div id="period-dimension-filter-fields" v-show="filtersExpanded" class="batch-filter-fields">
            <div class="batch-filter-row">
              <select v-model="year"><option value="all">全部年份</option><option v-for="value in yearOptions" :key="value" :value="value">{{ value }} 年</option></select>
              <select v-model="month"><option value="all">全部月份</option><option v-for="value in monthOptions" :key="value" :value="value">{{ Number(value) }} 月</option></select>
              <select v-model="week"><option value="all">全部周次</option><option v-for="value in weekOptions" :key="value" :value="String(value)">第 {{ value }} 周</option></select>
              <button class="btn primary" type="button" @click="applyFilters">查询</button>
            </div>
          </div>
        </div>

        <div class="table-wrap">
          <table class="period-summary-table">
            <thead><tr><th>策划周期</th><th>批次构成</th><th>AI 自动策划</th><th>人工策划</th><th>策划总数</th><th>完成数</th><th>失败数</th><th>最后更新</th><th>操作</th></tr></thead>
            <tbody>
              <template v-for="period in pagedPeriods" :key="period.cycleStart">
                <tr class="period-summary-row">
                  <td><div class="account-name-cell"><b>{{ cyclePeriodLabel(period.cycleStart) }}</b><small>{{ period.cycleStart }} 至 {{ period.cycleEnd }}</small></div></td>
                  <td><span class="tag blue">{{ period.batches.length }} 个批次</span></td>
                  <td><div class="period-type-stat"><b>{{ period.autoBatches.length }} 批</b><small>{{ modePlanningCount(period.autoBatches) }} 条策划</small></div></td>
                  <td><div class="period-type-stat"><b>{{ period.manualBatches.length }} 批</b><small>{{ modePlanningCount(period.manualBatches) }} 条策划</small></div></td>
                  <td><b>{{ period.planningCount }}</b></td>
                  <td class="batch-count" :class="{ completed: period.completedCount > 0 }">{{ period.completedCount }}</td>
                  <td class="batch-count" :class="{ failed: period.failedCount > 0 }">{{ period.failedCount }}</td>
                  <td>{{ formatDateTime(period.updatedAt) }}</td>
                  <td>
                    <div class="period-actions">
                      <button class="text-btn" type="button" :aria-expanded="expandedPeriod === period.cycleStart" @click="togglePeriod(period.cycleStart)">{{ expandedPeriod === period.cycleStart ? '收起批次' : '查看批次' }}</button>
                      <button class="text-btn" type="button" @click="openPeriod(period)">周期详情</button>
                    </div>
                  </td>
                </tr>
                <tr v-if="expandedPeriod === period.cycleStart" class="period-expansion-row">
                  <td colspan="9">
                    <div class="period-batch-panel">
                      <div class="table-wrap">
                        <table>
                          <thead><tr><th>批次</th><th>策划方式</th><th>批次周期</th><th>账号数</th><th>完成数</th><th>失败数</th><th>选题数</th><th>策划状态</th><th title="完成内容生产的账号数 / 总账号数">内容进度</th><th>更新时间</th><th>操作</th></tr></thead>
                          <tbody>
                            <tr v-for="batch in period.batches" :key="batch.id">
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
                              <td><button class="text-btn" type="button" @click="openBatch(batch)">查看详情</button></td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
              <tr v-if="periods.length === 0"><td colspan="9"><div class="empty-state"><b>暂无策划周期</b></div></td></tr>
            </tbody>
          </table>
        </div>
        <ListPagination v-model:page="page" v-model:page-size="pageSize" :total="periods.length" unit="个周期" class="list-pagination-inset" />
      </section>
    </template>
  </template>
</template>

<style scoped>
.legacy-account-view :deep(.result-tabs){display:none}
.period-summary-row>td{vertical-align:middle}
.period-type-stat{display:flex;flex-direction:column;gap:3px;white-space:nowrap}
.period-type-stat b{color:var(--neutral-700);font-size:13px}
.period-type-stat small{color:var(--neutral-400);font-size:11px}
.period-actions{display:flex;align-items:center;gap:12px;white-space:nowrap}
.period-expansion-row>td{padding:0!important;background:var(--neutral-50)}
.period-batch-panel{padding:12px 18px 18px;border-top:1px solid var(--neutral-200);border-bottom:1px solid var(--neutral-200)}
.period-batch-panel>.table-wrap{margin:0;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface)}
@media(max-width:980px){.period-summary-table{min-width:980px}.period-batch-panel{padding:12px}}
</style>
