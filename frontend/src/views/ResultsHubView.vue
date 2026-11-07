<script lang="ts">
import DateRangeFields from '../components/DateRangeFields.vue';
import QueryActions from '../components/QueryActions.vue';
import PeriodBatchDialog from '../components/planning/PeriodBatchDialog.vue';
import { defineComponent, type PropType } from '../compat/composition';
import { computed, ref, watch, onBeforeUnmount } from '../compat/composition';
import { useRoute, useRouter } from '../compat/router';
import { useActivePage } from '../composables/useActivePage';
import ContentProgress from '../components/ContentProgress.vue';
import ListPagination from '../components/ListPagination.vue';
import LoadingSkeleton from '../components/LoadingSkeleton.vue';
import PlanningExport from '../components/PlanningExport.vue';
import { api } from '../api';
import { formatDateTime } from '../planningTime';
import { usePlanningStore } from '../store';
import type { AutoFailure, BatchSummary, PlanningAccountSummary } from '../types';
import { statusTone } from '../ui/status';
import PlanningDetailsView from './PlanningDetailsView.vue';
import ResultFailureDrawer from '../components/planning/ResultFailureDrawer.vue';
import AccountResultsList from '../components/AccountResultsList.vue';
import type { PeriodSummary } from '../api/queries';
type ResultDimension = 'account' | 'period';
export default defineComponent({
    name: 'PlanningResultsPage',
    setup(props, context) {
        const store = usePlanningStore();
        const route = useRoute();
        const router = useRouter();
        const batches = ref<BatchSummary[]>([]);
        const loading = ref(false);
        const error = ref('');
        const filtersExpanded = ref(true);
        const expandedPeriod = ref<string | null>(null);
        const startDate = ref('');
        const endDate = ref('');
        const batchQuery = ref('');
        const dateFilterError = ref('');
        const appliedFilters = ref({
            startDate: '',
            endDate: '',
            batchQuery: ''
        });
        const failurePeriod = ref<PeriodSummary | null>(null);
        const page = ref(1);
        const pageSize = ref(20);
        const periodRows = ref<PeriodSummary[]>([]);
        const contextRows = ref<PeriodSummary[]>([]);
        const periodTotal = ref(0);
        let loadVersion = 0;
        let controller: AbortController | undefined;
        let resultsPaused = false;
        const requestedBatchId = computed(() => typeof route.query.batch === 'string' && /^\d+$/.test(route.query.batch) ? Number(route.query.batch) : null);
        const requestedAccountId = computed(() => typeof route.query.account === 'string' ? route.query.account.trim() : '');
        const requestedCycle = computed(() => typeof route.query.cycle === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(route.query.cycle) ? route.query.cycle : '');
        const showingBatchDetail = computed(() => requestedBatchId.value !== null);
        const showingAccountDetail = computed(() => !showingBatchDetail.value && Boolean(requestedAccountId.value));
        const showingPeriodDetail = computed(() => !showingBatchDetail.value && !showingAccountDetail.value && Boolean(requestedCycle.value));
        const dimension = computed<ResultDimension>(() => showingAccountDetail.value ? 'account' : route.query.dimension === 'period' || showingBatchDetail.value || showingPeriodDetail.value ? 'period' : 'account');
        const fromManualTask = computed(() => showingBatchDetail.value && route.query.from === 'manual');
        const fromCycleDetail = computed(() => showingBatchDetail.value && route.query.from === 'cycle' && Boolean(requestedCycle.value));
        function cycleWeekStart(date: string) {
            const value = new Date(`${date}T00:00:00Z`);
            value.setUTCDate(value.getUTCDate() - (value.getUTCDay() + 6) % 7);
            return value.toISOString().slice(0, 10);
        }
        function cycleWeekEnd(date: string) {
            const value = new Date(`${cycleWeekStart(date)}T00:00:00Z`);
            value.setUTCDate(value.getUTCDate() + 6);
            return value.toISOString().slice(0, 10);
        }
        const selectedPeriod = computed(() => contextRows.value.find(period => period.cycleStart === requestedCycle.value) ?? periodRows.value.find(period => period.cycleStart === requestedCycle.value) ?? null);
        const selectedBatch = computed(() => batches.value.find(batch => batch.id === requestedBatchId.value) ?? null);
        const periods = computed(() => periodRows.value);
        const pagedPeriods = computed(() => periodRows.value);
        function switchDimension(next: ResultDimension) {
            if (next === dimension.value && !showingBatchDetail.value && !showingPeriodDetail.value && !showingAccountDetail.value)
                return;
            expandedPeriod.value = null;
            void router.push({
                path: '/results',
                query: next === 'period' ? {
                    dimension: 'period'
                } : {}
            });
        }
        function applyFilters() {
            if (startDate.value && endDate.value && startDate.value > endDate.value) {
                dateFilterError.value = '开始时间不能晚于结束时间';
                return;
            }
            dateFilterError.value = '';
            appliedFilters.value = {
                startDate: startDate.value,
                endDate: endDate.value,
                batchQuery: batchQuery.value.trim()
            };
            expandedPeriod.value = null;
            page.value = 1;
        }
        function showFailureDetails(period: PeriodSummary) {
            failurePeriod.value = period;
        }
        function closeFailureDetails() {
            failurePeriod.value = null;
        }
        function togglePeriod(cycleStart: string) {
            expandedPeriod.value = expandedPeriod.value === cycleStart ? null : cycleStart;
        }
        function openPeriod(period: PeriodSummary) {
            void router.push({
                path: '/results',
                query: {
                    dimension: 'period',
                    cycle: period.cycleStart
                }
            });
        }
        function openAccount(account: PlanningAccountSummary) {
            void router.push({
                path: '/results',
                query: {
                    dimension: 'account',
                    account: account.account_id
                }
            });
        }
        function returnToPeriodList() {
            void router.push({
                path: '/results',
                query: {
                    dimension: 'period'
                }
            });
        }
        function openBatch(batch: BatchSummary, cycleStart?: string) {
            const query: Record<string, string> = {
                batch: String(batch.id),
                dimension: 'period'
            };
            if (cycleStart)
                query.cycle = cycleStart;
            void router.push({
                path: '/results',
                query
            });
        }
        function returnFromBatchDetail() {
            if (fromManualTask.value)
                void router.push('/manual');
            else if (fromCycleDetail.value)
                void router.push({
                    path: '/results',
                    query: {
                        dimension: 'period',
                        cycle: requestedCycle.value,
                        show_batches: '1'
                    }
                });
            else
                returnToPeriodList();
        }
        function openBatchFromCycle(batch: BatchSummary) {
            void router.push({
                path: '/results',
                query: {
                    dimension: 'period',
                    cycle: requestedCycle.value,
                    batch: String(batch.id),
                    from: 'cycle'
                }
            });
        }
        function returnToBatchCycle() {
            appliedFilters.value = {
                ...appliedFilters.value,
                batchQuery: ''
            };
            if (selectedBatch.value)
                void router.push({
                    path: '/results',
                    query: {
                        dimension: 'period',
                        cycle: cycleWeekStart(selectedBatch.value.cycle_start),
                        show_batches: '1'
                    }
                });
        }
        async function loadBatches() {
            if (resultsPaused || route.path !== '/results' || !store.databaseReady)
                return;
            const version = ++loadVersion;
            controller?.abort();
            controller = new AbortController();
            loading.value = true;
            error.value = '';
            try {
                if (showingAccountDetail.value) {
                    batches.value = [];
                    return;
                }
                if (showingBatchDetail.value || showingPeriodDetail.value) {
                    const response = await api.periodContext({
                        mode: showingBatchDetail.value ? 'batch' : 'cycle',
                        batch_id: requestedBatchId.value ?? undefined,
                        cycle_start: requestedCycle.value || undefined,
                        cycle_end: requestedCycle.value ? cycleWeekEnd(requestedCycle.value) : undefined,
                        filters: appliedFilters.value
                    });
                    if (version !== loadVersion)
                        return;
                    contextRows.value = response;
                    batches.value = response.flatMap(period => period.batches);
                }
                else {
                    const response = await api.periodPage({
                        page: page.value,
                        page_size: pageSize.value,
                        filters: appliedFilters.value
                    }, controller.signal);
                    if (version !== loadVersion)
                        return;
                    periodRows.value = response.items;
                    periodTotal.value = response.total;
                    const max = Math.max(1, Math.ceil(response.total / pageSize.value));
                    if (page.value > max)
                        page.value = max;
                }
            }
            catch (exc) {
                if (version === loadVersion)
                    error.value = exc instanceof Error ? exc.message : '读取策划结果失败';
            }
            finally {
                if (version === loadVersion)
                    loading.value = false;
            }
        }
        watch([() => store.databaseReady, dimension, requestedBatchId, requestedCycle, requestedAccountId], () => {
            if (store.databaseReady && (dimension.value === 'period' || showingAccountDetail.value))
                void loadBatches();
        }, {
            immediate: true
        });
        watch([page, pageSize, appliedFilters], () => {
            if (store.databaseReady && dimension.value === 'period' && !showingBatchDetail.value && !showingPeriodDetail.value)
                void loadBatches();
        });
        useActivePage(() => {
            const resumed = resultsPaused;
            resultsPaused = false;
            if (resumed && store.databaseReady && (dimension.value === 'period' || showingAccountDetail.value)) void loadBatches();
        }, () => {
            resultsPaused = true;
            ++loadVersion;
            controller?.abort();
        });
        const periodBatchDetail = computed(() => periods.value.find(period => period.cycleStart === expandedPeriod.value) || null);
        return {
            periodBatchDetail,
            formatDateTime,
            statusTone,
            store,
            route,
            batches,
            loading,
            error,
            filtersExpanded,
            expandedPeriod,
            startDate,
            endDate,
            batchQuery,
            dateFilterError,
            failurePeriod,
            page,
            pageSize,
            periodTotal,
            requestedAccountId,
            requestedCycle,
            showingBatchDetail,
            showingAccountDetail,
            showingPeriodDetail,
            dimension,
            fromManualTask,
            fromCycleDetail,
            cycleWeekStart,
            cycleWeekEnd,
            selectedPeriod,
            selectedBatch,
            periods,
            pagedPeriods,
            switchDimension,
            applyFilters,
            showFailureDetails,
            closeFailureDetails,
            togglePeriod,
            openPeriod,
            openAccount,
            returnToPeriodList,
            openBatch,
            returnFromBatchDetail,
            openBatchFromCycle,
            returnToBatchCycle
        };
    },
    components: {DateRangeFields, QueryActions, PeriodBatchDialog, AccountResultsList, LoadingSkeleton, PlanningDetailsView, PlanningExport, ContentProgress, ListPagination, ResultFailureDrawer}
});
</script>

<template>
<div class="vue2-component-root">
  <PeriodBatchDialog v-if="periodBatchDetail" :period="periodBatchDetail" @close="expandedPeriod = null" @open-batch="openBatch($event, periodBatchDetail.cycleStart); expandedPeriod = null" />
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

          <div id="period-dimension-filter-fields"  class="batch-filter-fields">
            <div class="batch-filter-row query-filter-grid" data-query-filters="standard">
              <DateRangeFields :start.sync="startDate" :end.sync="endDate" @query="applyFilters" />
              <label><span>批次号或批次 ID</span><input v-model="batchQuery" type="search" aria-label="批次号或批次 ID" placeholder="输入批次号或批次 ID" @keydown.enter.prevent="applyFilters" /></label>
              <QueryActions @query="applyFilters" @clear="startDate=''; endDate=''; batchQuery=''" />
            </div>
            <p v-if="dateFilterError" class="inline-error" role="alert">{{ dateFilterError }}</p>
          </div>
        </div>

        <div class="table-wrap">
          <table class="period-summary-table">
            <thead><tr><th>策划周期</th><th>批次构成</th><th>AI 自动策划</th><th>人工策划</th><th>账号数</th><th>完成数</th><th>失败数</th><th>最后更新</th><th>操作</th></tr></thead>
            <tbody>
              <template v-for="period in pagedPeriods" >
                <tr :key="(period.cycleStart) + '-0'" class="period-summary-row">
                  <td><div class="account-name-cell"><b>{{ period.cycleStart }} 至 {{ period.cycleEnd }}</b></div></td>
                  <td><span class="tag blue">{{ period.batches.length }} 个批次</span></td>
                  <td><div class="period-type-stat"><b>{{ period.autoBatches.length }} 批</b><small>{{ period.autoAccountCount }} 个账号</small></div></td>
                  <td><div class="period-type-stat"><b>{{ period.manualBatches.length }} 批</b><small>{{ period.manualAccountCount }} 个账号</small></div></td>
                  <td><b>{{ period.accountCount }}</b></td>
                  <td class="batch-count" :class="{ completed: period.completedCount > 0 }">{{ period.completedCount }}</td>
                  <td class="batch-count" :class="{ failed: period.failedCount > 0 }">{{ period.failedCount }}</td>
                  <td>{{ formatDateTime(period.updatedAt) }}</td>
                  <td><div class="period-actions">
                    <button class="text-btn" type="button" :aria-expanded="expandedPeriod === period.cycleStart" @click="togglePeriod(period.cycleStart)">查看批次</button>
                    <button class="text-btn" type="button" @click="openPeriod(period)">查看策划</button>
                    <PlanningExport inline :batches="period.batches" :filename="`策划明细_${period.cycleStart}_${period.cycleEnd}.xlsx`" />
                    <button v-if="period.failedCount > 0" class="text-btn failure-action" type="button" @click="showFailureDetails(period)">查看失败详情（{{ period.failedCount }}）</button>
                  </div></td>
                </tr>

              </template>
              <tr v-if="periods.length === 0"><td colspan="9"><div class="empty-state"><b>暂无符合条件的策划周期</b></div></td></tr>
            </tbody>
          </table>
        </div>
        <ListPagination :page.sync="page" :page-size.sync="pageSize" :total="periodTotal" unit="个周期" class="list-pagination-inset" />
      </section>
    </template>
  </template>

  <ResultFailureDrawer v-if="failurePeriod" :failure-period="failurePeriod" @close="closeFailureDetails" />
</div>
</template>

<style scoped>
.legacy-account-view ::v-deep .result-tabs{display:none}
.batch-filter-row>label{display:flex;min-width:0;flex-direction:column;gap:6px;color:var(--neutral-500);font-size:12px;font-weight:600}
.batch-filter-row>label>input{width:100%;box-sizing:border-box}
.failure-action{color:var(--danger)!important}
.period-summary-row>td{vertical-align:middle}.period-type-stat{display:flex;flex-direction:column;gap:3px;white-space:nowrap}.period-type-stat b{color:var(--neutral-700);font-size:13px}.period-type-stat small{color:var(--neutral-400);font-size:11px}.period-actions{display:flex;align-items:center;gap:12px;white-space:nowrap}
.period-expansion-row>td{padding:0!important;background:var(--neutral-50)}.period-batch-panel{padding:14px 18px 18px;border-top:1px solid var(--neutral-200);border-bottom:1px solid var(--neutral-200)}.period-batch-panel>.table-wrap{margin:0;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface)}
@media(max-width:980px){.period-summary-table{min-width:980px}.period-batch-panel{padding:12px}}
</style>
