<script>
import DateRangeFields from '../components/DateRangeFields.vue';
import QueryActions from '../components/QueryActions.vue';
import AccountTypeBadge from '../components/AccountTypeBadge.vue';
import LoadingSkeleton from '../components/LoadingSkeleton.vue';
import ListPagination from '../components/ListPagination.vue';
import HoverHint from '../components/HoverHint.vue';
import PlanningResultStats from '../components/planning/PlanningResultStats.vue';
import PlanningWeekCalendar from '../components/planning/PlanningWeekCalendar.vue';
import { weekStart, weekEnd, cyclePeriodLabel } from '../ui/planningCalendar';
import PlanDetailDrawer from '../components/planning/PlanDetailDrawer.vue';
import { api } from '../api';
import { bindPageActivity } from "../services/pageActivity";
import { productionStatusLabel } from '../ui/slotContentStatus';
import { formatDateTime } from '../planningTime';
export default {
  props: {
    mode: {
      required: false,
      type: null,
      default: 'cycle'
    },
    cycleStart: {
      required: true,
      type: String
    },
    cycleEnd: {
      required: true,
      type: String
    },
    batches: {
      required: true,
      type: Array
    },
    accountId: {
      required: false,
      type: String,
      default: ''
    },
    returnLabel: {
      required: false,
      type: String,
      default: ''
    },
    initialBatchesExpanded: {
      required: false,
      type: Boolean,
      default: false
    },
    showCycleLink: {
      required: false,
      type: Boolean,
      default: false
    }
  },
  components: {
    DateRangeFields,
    QueryActions,
    HoverHint,
    LoadingSkeleton,
    PlanningResultStats,
    ListPagination,
    PlanningWeekCalendar,
    AccountTypeBadge,
    PlanDetailDrawer
  },
  data() {
    return {
      loading: false,
      error: '',
      pageItems: [],
      resultTotal: 0,
      resultSummary: {
        accounts: 0,
        batches: 0,
        topics: 0
      },
      resultDistribution: [],
      resultContentTypes: [],
      accountCatalog: [],
      expandedAccounts: new Set(),
      filtersExpanded: true,
      batchesExpanded: null,
      batchPage: 1,
      batchPageSize: 10,
      accountKeyword: '',
      contentType: 'all',
      selectedPlan: null,
      dateStart: '',
      dateEnd: '',
      dateFilterError: '',
      appliedFilters: {
        account: '',
        start: '',
        end: '',
        batch: 'all',
        planType: 'all',
        contentType: 'all'
      },
      page: 1,
      pageSize: 20,
      historyPage: 1,
      historyPageSize: 20,
      loadRequest: 0,
      detailRequest: undefined,
      productionTimer: undefined,
      visited: false
    };
  },
  computed: {
    pagedCycleBatches() {
      return this.batches.slice((this.batchPage - 1) * this.batchPageSize, this.batchPage * this.batchPageSize);
    },
    isBatchMode() {
      return this.mode === 'batch';
    },
    isAccountMode() {
      return this.mode === 'account';
    },
    detailTitle() {
      return this.isAccountMode ? '账号策划详情' : this.isBatchMode ? '批次策划详情' : '周期策划详情';
    },
    currentBatch() {
      return this.isBatchMode ? this.batches[0] ?? null : null;
    },
    batchById() {
      return new Map(this.batches.map(batch => [batch.id, batch]));
    },
    productionItems() {
      return this.pageItems;
    },
    backLabel() {
      return this.returnLabel || (this.isAccountMode ? '返回账号列表' : '返回时间列表');
    },
    fixedPlanType() {
      return this.isBatchMode ? this.currentBatch?.plan_type ?? null : null;
    },
    scopeLabel() {
      if (this.isAccountMode) return `${this.accountProfile(this.accountId)?.account_name || this.pageItems[0]?.account_name || this.accountId} · ${this.accountId}`;
      if (this.currentBatch) return [this.currentBatch.task_name, this.currentBatch.batch_code].filter(Boolean).join(' · ');
      return cyclePeriodLabel(this.cycleStart);
    },
    scopePlanType() {
      return this.fixedPlanType === 'manual' ? '人工策划' : 'AI 自动策划';
    },
    contentTypes() {
      return this.resultContentTypes;
    },
    filteredItems() {
      return this.pageItems;
    },
    accountGroups() {
      const groups = new Map();
      for (const item of this.filteredItems) {
        const existing = groups.get(item.account_id);
        if (existing) existing.items.push(item);else groups.set(item.account_id, {
          account_id: item.account_id,
          account_name: item.account_name,
          lifecycle_stage: item.lifecycle_stage || '—',
          profile: this.accountProfile(item.account_id),
          items: [item]
        });
      }
      return [...groups.values()].map(group => ({
        ...group,
        items: group.items.sort((a, b) => a.publish_date.localeCompare(b.publish_date) || a.id - b.id)
      }));
    },
    pagedAccountGroups() {
      return this.accountGroups;
    },
    accountWeeks() {
      return this.accountGroups.length ? this.weeksFor(this.accountGroups[0]) : [];
    },
    pagedAccountWeeks() {
      return this.accountWeeks;
    },
    cyclePeriodLabel() {
      return cyclePeriodLabel;
    },
    formatDateTime() {
      return formatDateTime;
    }
  },
  methods: {
    accountProfile(accountId) {
      return this.accountCatalog.find(account => account.account_id === accountId);
    },
    accountTypeLabel(profile) {
      return profile?.account_type || (profile?.certified === true ? '认证' : profile?.certified === false ? '非认证' : '—');
    },
    weeksFor(group) {
      const weeks = new Map();
      for (const item of group.items) {
        const key = weekStart(item.publish_date);
        const items = weeks.get(key);
        if (items) items.push(item);else weeks.set(key, [item]);
      }
      return [...weeks].map(([start, items]) => ({
        start,
        end: weekEnd(start),
        items
      })).sort((a, b) => b.start.localeCompare(a.start));
    },
    toggleAccount(accountId) {
      const next = new Set(this.expandedAccounts);
      if (next.has(accountId)) next.delete(accountId);else next.add(accountId);
      this.expandedAccounts = next;
    },
    updatePlan(item) {
      this.pageItems = this.pageItems.map(record => record.id === item.id ? {
        ...record,
        ...item
      } : record);
      void this.load(true);
    },
    async load(silent = false) {
      const request = ++this.loadRequest;
      this.detailRequest?.abort();
      this.detailRequest = new AbortController();
      if (!silent) this.loading = true;
      this.error = '';
      try {
        const response = await api.planPage({
          mode: this.mode,
          batch_ids: this.mode === 'cycle' ? this.batches.map(batch => batch.id) : undefined,
          account_id: this.isAccountMode ? this.accountId : undefined,
          batch_id: this.isBatchMode ? this.currentBatch?.id : undefined,
          cycle_start: this.mode === 'cycle' ? this.cycleStart : undefined,
          cycle_end: this.mode === 'cycle' ? this.cycleEnd : undefined,
          page: this.isAccountMode ? this.historyPage : this.page,
          page_size: this.isAccountMode ? this.historyPageSize : this.pageSize,
          filters: this.appliedFilters
        }, this.detailRequest.signal);
        if (request !== this.loadRequest) return;
        const currentPage = this.isAccountMode ? this.historyPage : this.page;
        const currentSize = this.isAccountMode ? this.historyPageSize : this.pageSize;
        const maximum = Math.max(1, Math.ceil(response.total / currentSize));
        if (currentPage.value > maximum) {
          currentPage.value = maximum;
          return;
        }
        this.pageItems = response.items;
        this.resultTotal = response.total;
        this.resultSummary = response.summary;
        this.resultDistribution = response.distribution;
        this.resultContentTypes = response.content_types;
        this.accountCatalog = response.accounts;
        if (this.isAccountMode) this.expandedAccounts = new Set([this.accountId]);
      } catch (exc) {
        if (request === this.loadRequest) this.error = exc instanceof Error ? exc.message : '读取策划明细失败';
      } finally {
        if (request === this.loadRequest) this.loading = false;
      }
    },
    applyFilters() {
      if (this.isAccountMode && this.dateStart && this.dateEnd && this.dateStart > this.dateEnd) {
        this.dateFilterError = '开始日期不能晚于结束日期';
        return;
      }
      this.dateFilterError = '';
      this.appliedFilters = {
        account: this.isAccountMode ? '' : this.accountKeyword,
        start: this.isAccountMode ? this.dateStart : '',
        end: this.isAccountMode ? this.dateEnd : '',
        batch: this.isBatchMode ? String(this.currentBatch?.id) : 'all',
        planType: this.fixedPlanType ?? 'all',
        contentType: this.contentType
      };
      this.page = 1;
      this.historyPage = 1;
    },
    emit(...args) {
      return this.$emit(...args);
    }
  },
  created() {
    this.batchesExpanded = this.initialBatchesExpanded;
    this.$watch(() => [this.mode, this.accountId, this.cycleStart, this.batches.map(batch => batch.id).join(',')], () => {
      this.selectedPlan = null;
    });
    this.$watch(() => [this.mode, this.accountId, this.cycleStart, this.batches.map(batch => batch.id).join(',')], () => {
      this.accountKeyword = '';
      this.contentType = 'all';
      this.dateStart = this.isAccountMode ? this.cycleStart : '';
      this.dateEnd = this.isAccountMode && this.cycleStart ? weekEnd(this.cycleStart) : '';
      this.dateFilterError = '';
      this.filtersExpanded = true;
      this.applyFilters();
      this.expandedAccounts = new Set();
      this.selectedPlan = null;
      void this.load();
    }, {
      immediate: true
    });
    this.$watch(() => this.pageSize, () => {
      this.page = 1;
    });
    this.$watch(() => [this.page, this.pageSize, this.historyPage, this.historyPageSize, this.appliedFilters], () => {
      void this.load();
    });
    this.$watch(() => this.historyPageSize, () => {
      this.historyPage = 1;
    });
    bindPageActivity(this, () => {
      if (this.visited) void this.load(true);
      this.visited = true;
      this.productionTimer = window.setInterval(() => {
        if (!this.loading && this.productionItems.some(item => item.topic_id && ['待生产', '生产中'].includes(productionStatusLabel(item)))) void this.load(true);
      }, 3000);
    }, () => {
      this.loadRequest++;
      this.detailRequest?.abort();
      if (this.productionTimer !== undefined) window.clearInterval(this.productionTimer);
    });
  }
};
</script>

<template>
<div class="vue2-component-root">
  <section class="card planning-detail-card">
    <div class="card-head planning-detail-head">
      <div class="planning-detail-heading">
        <h2>{{ detailTitle }}</h2>
        <div v-if="isBatchMode" class="planning-detail-scope planning-batch-scope">
          <HoverHint text="周期" :show-icon="false" class="tag gray planning-context-tag">{{ cyclePeriodLabel(cycleStart) }}</HoverHint>
          <HoverHint text="策划方式" :show-icon="false" :class="['tag', 'planning-context-tag', fixedPlanType === 'manual' ? 'auxiliary' : 'blue']">{{ scopePlanType }}</HoverHint>
          <HoverHint text="批次号" :show-icon="false" class="tag gray planning-context-tag"><span class="planning-batch-code">{{ currentBatch?.batch_code || '—' }}</span></HoverHint>
        </div>
        <div v-else-if="isAccountMode" class="planning-detail-scope">
          <HoverHint text="账号" :show-icon="false" class="tag gray planning-context-tag"><span class="planning-scope-label">{{ scopeLabel }}</span></HoverHint>
          <HoverHint text="投放日期" :show-icon="false" class="tag gray planning-context-tag">{{ appliedFilters.start || appliedFilters.end ? `${appliedFilters.start || '不限'} 至 ${appliedFilters.end || '不限'}` : '全部日期' }}</HoverHint>
        </div>
        <div v-else class="planning-detail-scope"><HoverHint text="周期" :show-icon="false" class="tag gray planning-context-tag">{{ scopeLabel }}</HoverHint></div>
      </div>
      <div class="planning-detail-actions">
        <button v-if="isBatchMode && showCycleLink" class="btn" type="button" @click="emit('view-cycle')">查看所有批次</button>
        <button class="btn" type="button" @click="emit('back')">{{ backLabel }}</button>
      </div>
    </div>

    <LoadingSkeleton v-if="loading" :rows="8" />
    <div v-else-if="error" class="banner error-banner" role="alert">{{ error }}</div>
    <template v-else>
      <div class="detail-filter-shell">

        <div  class="detail-filter-fields query-filter-grid" data-query-filters="compact">
          <label v-if="!isAccountMode"><span>账号 ID 或昵称</span><input v-model="accountKeyword" type="search" placeholder="输入账号 ID 或昵称" /></label>
          <DateRangeFields v-if="isAccountMode" :start.sync="dateStart" :end.sync="dateEnd" @query="applyFilters" />
          <div class="query-filter-tail">
            <label><span>选题二级分类</span><select v-model="contentType"><option value="all">全部选题二级分类</option><option v-for="value in contentTypes" :key="value" :value="value">{{ value }}</option></select></label>
            <QueryActions @query="applyFilters" @clear="accountKeyword=''; dateStart=''; dateEnd=''; contentType='all'" />
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
          <tbody><tr v-for="batch in pagedCycleBatches" :key="batch.id"><td><div class="cycle-batch-identity"><b>{{ batch.task_name || '—' }}</b><small>{{ batch.batch_code }}</small></div></td><td>{{ batch.plan_type === 'manual' ? '人工策划' : '自动策划' }}</td><td>{{ batch.account_count }}</td><td>{{ batch.planning_status || batch.status }}</td><td>{{ formatDateTime(batch.updated_at || batch.created_at) }}</td><td><button class="text-btn" type="button" @click="emit('open-batch', batch)">查看策划</button></td></tr><tr v-if="!batches.length"><td colspan="6"><div class="empty-state">暂无批次</div></td></tr></tbody>
        </table></div>
        <ListPagination v-if="batches.length > 10" :page.sync="batchPage" :page-size.sync="batchPageSize" :total="batches.length" unit="个批次" />
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
        <ListPagination v-if="resultTotal" :page.sync="historyPage" :page-size.sync="historyPageSize" :total="resultTotal" unit="周" class="list-pagination-inset" />
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
      <ListPagination v-if="!isAccountMode && resultTotal" :page.sync="page" :page-size.sync="pageSize" :total="resultTotal" unit="个账号" class="list-pagination-inset" />
    </template>
  </section>
  <PlanDetailDrawer v-if="selectedPlan" :plan="selectedPlan" @close-plan="selectedPlan = null" @plan-updated="updatePlan" />
</div>
</template>

<style scoped>
.cycle-batch-toggle{margin-top:3px;align-self:flex-start;font-size:12px}.cycle-batch-list{margin:0 20px 16px;border:1px solid var(--neutral-200);border-radius:8px;overflow:hidden}.cycle-batch-title{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:var(--neutral-50);font-size:13px}.cycle-batch-title span,.cycle-batch-identity small{color:var(--neutral-500);font-size:12px}.cycle-batch-identity{display:flex;flex-direction:column;gap:3px}.cycle-batch-list table{min-width:720px}
.cycle-batch-action{display:flex;justify-content:flex-end;margin:-8px 20px 12px}
.account-plan-table-wrap{margin:0 20px 20px}.account-plan-table{table-layout:fixed;min-width:1180px}.account-plan-table th,.account-plan-table td{padding:14px 12px;vertical-align:top;line-height:22px}.account-plan-table td{color:var(--neutral-700)}.account-plan-date{white-space:nowrap;font-variant-numeric:tabular-nums}.account-plan-text{white-space:pre-wrap;overflow-wrap:anywhere}.account-plan-batch{overflow-wrap:anywhere}.account-plan-batch>span{display:block}.account-plan-batch>small{margin-top:3px;font-size:12px;line-height:18px}.account-plan-table .empty-state{text-align:center;padding:32px 12px;color:var(--neutral-400)}
@media(max-width:980px){.account-plan-table-wrap{margin:0 12px 16px}}
.planning-detail-head{align-items:flex-start;flex-wrap:wrap}.planning-detail-heading{flex:1 1 260px;min-width:0}.planning-detail-actions{display:flex;flex:0 0 auto;align-items:center;align-self:flex-start;justify-content:flex-end;flex-wrap:wrap;gap:8px;max-width:100%;margin-left:auto}.planning-detail-actions .btn{white-space:nowrap}.planning-detail-scope .planning-context-tag{min-width:0;max-width:100%;min-height:24px;padding:3px 8px;border-radius:6px;background:var(--neutral-100);color:var(--neutral-500);font-size:12px;line-height:18px;font-weight:500}.planning-batch-code{min-width:0;max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.planning-batch-scope .planning-context-tag.orange{background:var(--warning-bg);color:var(--warning)}.planning-batch-scope .planning-context-tag.blue{background:var(--primary-50);color:var(--primary-600)}
.planning-detail-scope{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-top:6px;min-width:0}.planning-scope-label{max-width:560px;overflow:hidden;text-overflow:ellipsis;font-size:12px}.planning-week-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border-top:1px solid var(--neutral-200);background:var(--neutral-50)}.planning-week-heading>span{color:var(--neutral-400);font-size:11px}.detail-query-btn{align-self:end;height:36px;min-width:80px;white-space:nowrap}
.detail-filter-shell{margin:0 20px 16px;padding:12px 14px;border:1px solid var(--neutral-200);border-radius:10px;background:var(--surface)}
.planning-detail-card>.detail-filter-shell{margin-top:16px;margin-bottom:0}
.detail-filter-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr)) auto;gap:12px;align-items:end;margin-top:12px}.detail-filter-fields label{display:flex;flex-direction:column;gap:6px;min-width:0}.detail-filter-fields label>span{color:var(--neutral-500);font-size:12px}.detail-filter-fields input,.detail-filter-fields select{width:100%;height:36px}
.planning-account-list{display:grid;gap:8px;padding:0 20px 20px}.planning-account-card{overflow:hidden;border:1px solid var(--neutral-200);border-radius:10px;background:var(--surface);transition:border-color .14s ease,background .14s ease}.planning-account-card:hover{border-color:var(--neutral-300)}.planning-account-card.expanded{border-color:var(--primary-200)}
.planning-account-head{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:12px 14px}.planning-account-main{min-width:0;flex:1}.planning-account-identity{display:flex;flex-direction:column;gap:5px;min-width:0}.planning-account-title{display:flex;align-items:center;flex-wrap:wrap;gap:7px}.planning-account-title>strong{color:var(--neutral-900);font-size:14px;line-height:20px}.planning-account-meta{display:flex;align-items:center;flex-wrap:wrap;color:var(--neutral-400);font-size:11px;line-height:17px}.planning-account-meta span{display:inline-flex;align-items:center;min-width:0}.planning-account-meta span+span::before{display:inline-block;flex:none;width:1px;height:10px;margin:0 8px;background:var(--neutral-200);content:''}.planning-account-persona-inline{max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.planning-account-persona-inline b{margin-right:4px;color:var(--neutral-500);font-size:10px;font-weight:500}.planning-account-actions{display:flex;align-items:center;gap:8px;flex:none}.planning-plan-count{color:var(--neutral-500);font-size:11px;white-space:nowrap}.planning-expand-btn{display:inline-flex;align-items:center;gap:5px;height:30px;padding:0 9px;border:1px solid var(--neutral-200);border-radius:7px;background:var(--surface);color:var(--neutral-600);font-size:11px;cursor:pointer;transition:border-color .14s ease,background .14s ease,color .14s ease}.planning-expand-btn:hover{border-color:var(--primary-200);background:var(--primary-50);color:var(--primary-600)}.planning-expand-btn:focus-visible{outline:2px solid var(--primary-300);outline-offset:2px}.planning-expand-btn svg{transition:transform .14s ease}.planning-expand-btn svg.expanded{transform:rotate(180deg)}
@media(max-width:980px){.detail-filter-shell{margin:0 12px 14px}.planning-account-list{padding:0 12px 16px}.planning-account-head{align-items:flex-start;flex-direction:column;gap:10px;padding:12px}.planning-account-actions{width:100%;justify-content:flex-end}.planning-account-persona-inline{max-width:360px}}
@media(max-width:580px){.detail-filter-fields{grid-template-columns:minmax(0,1fr) auto}.detail-filter-fields label:first-child{grid-column:1/-1}.planning-account-meta{row-gap:2px}.planning-account-persona-inline{max-width:220px}.planning-account-actions{justify-content:space-between}}
</style>
