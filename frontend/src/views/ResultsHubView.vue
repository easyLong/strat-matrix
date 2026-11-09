<script>
import DateRangeFields from '../components/DateRangeFields.vue';
import QueryActions from '../components/QueryActions.vue';
import PeriodBatchDialog from '../components/planning/PeriodBatchDialog.vue';
import { planningRoute, planningRouter } from '../compat/router';
import { bindPageActivity } from "../services/pageActivity";
import ContentProgress from '../components/ContentProgress.vue';
import ListPagination from '../components/ListPagination.vue';
import LoadingSkeleton from '../components/LoadingSkeleton.vue';
import PlanningExport from '../components/PlanningExport.vue';
import { api } from '../api';
import { formatDateTime } from '../planningTime';
import { usePlanningStore } from '../store';
import { statusTone } from '../ui/status';
import PlanningDetailsView from './PlanningDetailsView.vue';
import ResultFailureDrawer from '../components/planning/ResultFailureDrawer.vue';
import AccountResultsList from '../components/AccountResultsList.vue';
export default {
  name: 'PlanningResultsPage',
  components: {
    DateRangeFields,
    QueryActions,
    PeriodBatchDialog,
    AccountResultsList,
    LoadingSkeleton,
    PlanningDetailsView,
    PlanningExport,
    ContentProgress,
    ListPagination,
    ResultFailureDrawer
  },
  data() {
    return {
      batches: [],
      loading: false,
      error: '',
      filtersExpanded: true,
      expandedPeriod: null,
      startDate: '',
      endDate: '',
      batchQuery: '',
      dateFilterError: '',
      appliedFilters: {
        startDate: '',
        endDate: '',
        batchQuery: ''
      },
      failurePeriod: null,
      page: 1,
      pageSize: 20,
      periodRows: [],
      contextRows: [],
      periodTotal: 0,
      loadVersion: 0,
      controller: undefined,
      resultsPaused: false
    };
  },
  computed: {
    store() {
      return usePlanningStore();
    },
    route() {
      return planningRoute(this);
    },
    router() {
      return planningRouter(this);
    },
    requestedBatchId() {
      return typeof this.route.query.batch === 'string' && /^\d+$/.test(this.route.query.batch) ? Number(this.route.query.batch) : null;
    },
    requestedAccountId() {
      return typeof this.route.query.account === 'string' ? this.route.query.account.trim() : '';
    },
    requestedCycle() {
      return typeof this.route.query.cycle === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(this.route.query.cycle) ? this.route.query.cycle : '';
    },
    showingBatchDetail() {
      return this.requestedBatchId !== null;
    },
    showingAccountDetail() {
      return !this.showingBatchDetail && Boolean(this.requestedAccountId);
    },
    showingPeriodDetail() {
      return !this.showingBatchDetail && !this.showingAccountDetail && Boolean(this.requestedCycle);
    },
    dimension() {
      return this.showingAccountDetail ? 'account' : this.route.query.dimension === 'period' || this.showingBatchDetail || this.showingPeriodDetail ? 'period' : 'account';
    },
    fromManualTask() {
      return this.showingBatchDetail && this.route.query.from === 'manual';
    },
    fromCycleDetail() {
      return this.showingBatchDetail && this.route.query.from === 'cycle' && Boolean(this.requestedCycle);
    },
    selectedPeriod() {
      return this.contextRows.find(period => period.cycleStart === this.requestedCycle) ?? this.periodRows.find(period => period.cycleStart === this.requestedCycle) ?? null;
    },
    selectedBatch() {
      return this.batches.find(batch => batch.id === this.requestedBatchId) ?? null;
    },
    periods() {
      return this.periodRows;
    },
    pagedPeriods() {
      return this.periodRows;
    },
    periodBatchDetail() {
      return this.periods.find(period => period.cycleStart === this.expandedPeriod) || null;
    },
    formatDateTime() {
      return formatDateTime;
    },
    statusTone() {
      return statusTone;
    }
  },
  methods: {
    cycleWeekStart(date) {
      const value = new Date(`${date}T00:00:00Z`);
      value.setUTCDate(value.getUTCDate() - (value.getUTCDay() + 6) % 7);
      return value.toISOString().slice(0, 10);
    },
    cycleWeekEnd(date) {
      const value = new Date(`${this.cycleWeekStart(date)}T00:00:00Z`);
      value.setUTCDate(value.getUTCDate() + 6);
      return value.toISOString().slice(0, 10);
    },
    switchDimension(next) {
      if (next === this.dimension && !this.showingBatchDetail && !this.showingPeriodDetail && !this.showingAccountDetail) return;
      this.expandedPeriod = null;
      void this.router.push({
        path: '/results',
        query: next === 'period' ? {
          dimension: 'period'
        } : {}
      });
    },
    applyFilters() {
      if (this.startDate && this.endDate && this.startDate > this.endDate) {
        this.dateFilterError = '开始时间不能晚于结束时间';
        return;
      }
      this.dateFilterError = '';
      this.appliedFilters = {
        startDate: this.startDate,
        endDate: this.endDate,
        batchQuery: this.batchQuery.trim()
      };
      this.expandedPeriod = null;
      this.page = 1;
    },
    showFailureDetails(period) {
      this.failurePeriod = period;
    },
    closeFailureDetails() {
      this.failurePeriod = null;
    },
    togglePeriod(cycleStart) {
      this.expandedPeriod = this.expandedPeriod === cycleStart ? null : cycleStart;
    },
    openPeriod(period) {
      void this.router.push({
        path: '/results',
        query: {
          dimension: 'period',
          cycle: period.cycleStart
        }
      });
    },
    openAccount(account) {
      void this.router.push({
        path: '/results',
        query: {
          dimension: 'account',
          account: account.account_id
        }
      });
    },
    returnToPeriodList() {
      void this.router.push({
        path: '/results',
        query: {
          dimension: 'period'
        }
      });
    },
    openBatch(batch, cycleStart) {
      const query = {
        batch: String(batch.id),
        dimension: 'period'
      };
      if (cycleStart) query.cycle = cycleStart;
      void this.router.push({
        path: '/results',
        query
      });
    },
    returnFromBatchDetail() {
      if (this.fromManualTask) void this.router.push('/manual');else if (this.fromCycleDetail) void this.router.push({
        path: '/results',
        query: {
          dimension: 'period',
          cycle: this.requestedCycle,
          show_batches: '1'
        }
      });else this.returnToPeriodList();
    },
    openBatchFromCycle(batch) {
      void this.router.push({
        path: '/results',
        query: {
          dimension: 'period',
          cycle: this.requestedCycle,
          batch: String(batch.id),
          from: 'cycle'
        }
      });
    },
    returnToBatchCycle() {
      this.appliedFilters = {
        ...this.appliedFilters,
        batchQuery: ''
      };
      if (this.selectedBatch) void this.router.push({
        path: '/results',
        query: {
          dimension: 'period',
          cycle: this.cycleWeekStart(this.selectedBatch.cycle_start),
          show_batches: '1'
        }
      });
    },
    async loadBatches() {
      if (this.resultsPaused || this.route.path !== '/results' || !this.store.databaseReady) return;
      const version = ++this.loadVersion;
      this.controller?.abort();
      this.controller = new AbortController();
      this.loading = true;
      this.error = '';
      try {
        if (this.showingAccountDetail) {
          this.batches = [];
          return;
        }
        if (this.showingBatchDetail || this.showingPeriodDetail) {
          const response = await api.periodContext({
            mode: this.showingBatchDetail ? 'batch' : 'cycle',
            batch_id: this.requestedBatchId ?? undefined,
            cycle_start: this.requestedCycle || undefined,
            cycle_end: this.requestedCycle ? this.cycleWeekEnd(this.requestedCycle) : undefined,
            filters: this.appliedFilters
          });
          if (version !== this.loadVersion) return;
          this.contextRows = response;
          this.batches = response.flatMap(period => period.batches);
        } else {
          const response = await api.periodPage({
            page: this.page,
            page_size: this.pageSize,
            filters: this.appliedFilters
          }, this.controller.signal);
          if (version !== this.loadVersion) return;
          this.periodRows = response.items;
          this.periodTotal = response.total;
          const max = Math.max(1, Math.ceil(response.total / this.pageSize));
          if (this.page > max) this.page = max;
        }
      } catch (exc) {
        if (version === this.loadVersion) this.error = exc instanceof Error ? exc.message : '读取策划结果失败';
      } finally {
        if (version === this.loadVersion) this.loading = false;
      }
    }
  },
  created() {
    this.$watch(() => [this.store.databaseReady, this.dimension, this.requestedBatchId, this.requestedCycle, this.requestedAccountId], () => {
      if (this.store.databaseReady && (this.dimension === 'period' || this.showingAccountDetail)) void this.loadBatches();
    }, {
      immediate: true
    });
    this.$watch(() => [this.page, this.pageSize, this.appliedFilters], () => {
      if (this.store.databaseReady && this.dimension === 'period' && !this.showingBatchDetail && !this.showingPeriodDetail) void this.loadBatches();
    });
    bindPageActivity(this, () => {
      const resumed = this.resultsPaused;
      this.resultsPaused = false;
      if (resumed && this.store.databaseReady && (this.dimension === 'period' || this.showingAccountDetail)) void this.loadBatches();
    }, () => {
      this.resultsPaused = true;
      ++this.loadVersion;
      this.controller?.abort();
    });
  }
};
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
