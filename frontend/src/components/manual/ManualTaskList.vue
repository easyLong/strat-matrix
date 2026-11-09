<script>
import DateRangeFields from '../DateRangeFields.vue';
import QueryActions from '../QueryActions.vue';
import ManualTaskTable from '../ManualTaskTable.vue';
import ListPagination from '../ListPagination.vue';
import { api } from '../../api';
import { bindPageActivity } from "../../services/pageActivity";
import { usePlanningStore } from '../../store';
import { createAsyncPage } from "../../services/asyncPage";
import { manualContentLabel } from '../../ui/manualTask';
export default {
  components: {
    DateRangeFields,
    QueryActions,
    ManualTaskTable,
    ListPagination
  },
  data() {
    return {
      error: '',
      tasks: [],
      taskTotal: 0,
      savedTaskList: null,
      restoreTaskListPending: null,
      manualDisposed: false,
      taskPage: null,
      taskPageSize: null,
      taskFilters: null,
      appliedTaskFilters: null,
      taskDateError: '',
      tasksLoading: false,
      refreshTimer: undefined,
      taskQuery: null
    };
  },
  computed: {
    store() {
      return usePlanningStore();
    },
    taskListRef: {
      cache: false,
      get() {
        return this.$refs.taskListRef || null;
      }
    },
    taskFiltersActive() {
      return Object.values(this.appliedTaskFilters).some(Boolean);
    },
    taskContentStatuses() {
      return [...new Set(['待分配', '待生成', '生成中', '已完成', '生成失败', '部分失败', ...this.tasks.map(manualContentLabel)])];
    },
    filteredTasks() {
      return this.tasks;
    },
    pagedTasks() {
      return this.tasks;
    }
  },
  methods: {
    applyTaskFilters() {
      this.taskDateError = '';
      if (this.taskFilters.dateStart && this.taskFilters.dateEnd && this.taskFilters.dateStart > this.taskFilters.dateEnd) {
        this.taskDateError = '投放开始日期不能晚于结束日期';
        return;
      }
      this.appliedTaskFilters = {
        ...this.taskFilters,
        batch: this.taskFilters.batch.trim(),
        creator: this.taskFilters.creator.trim()
      };
      this.taskPage = 1;
    },
    async loadTasks() {
      const loaded = await this.taskQuery.load();
      if (!loaded || this.manualDisposed) return;
      this.error = '';
      const maximum = Math.max(1, Math.ceil(this.taskTotal / this.taskPageSize));
      if (this.taskPage > maximum) {
        this.taskPage = maximum;
        return;
      }
      if (this.restoreTaskListPending) {
        this.restoreTaskListPending = false;
        await this.$nextTick();
        if (this.manualDisposed) return;
        const table = this.taskListRef?.querySelector('.manual-task-table-wrap');
        if (table && this.savedTaskList) {
          table.scrollTop = this.savedTaskList.tableScrollTop;
          table.scrollLeft = this.savedTaskList.tableScrollLeft;
        }
        window.scrollTo({
          top: this.savedTaskList?.scrollY ?? 0,
          behavior: 'instant'
        });
      }
    },
    rememberTaskList() {
      const table = this.taskListRef?.querySelector('.manual-task-table-wrap');
      this.store.manualTaskListState = {
        page: this.taskPage,
        pageSize: this.taskPageSize,
        filters: {
          ...this.taskFilters
        },
        appliedFilters: {
          ...this.appliedTaskFilters
        },
        scrollY: window.scrollY,
        tableScrollTop: table?.scrollTop ?? 0,
        tableScrollLeft: table?.scrollLeft ?? 0
      };
    },
    selectTask(task) {
      this.rememberTaskList();
      this.$emit('plan-details', task);
    }
  },
  created() {
    this.savedTaskList = this.store.manualTaskListState;
    this.restoreTaskListPending = Boolean(this.savedTaskList);
    this.taskPage = this.savedTaskList?.page ?? 1;
    this.taskPageSize = this.savedTaskList?.pageSize ?? 10;
    this.taskFilters = {
      ...(this.savedTaskList?.filters ?? {
        batch: '',
        dateStart: '',
        dateEnd: '',
        creator: '',
        contentStatus: ''
      })
    };
    this.appliedTaskFilters = {
      ...(this.savedTaskList?.appliedFilters ?? this.taskFilters)
    };
    this.taskQuery = createAsyncPage(this, signal => api.manualTaskPage({
      page: this.taskPage,
      page_size: this.taskPageSize,
      filters: this.appliedTaskFilters
    }, signal), {
      items: "tasks",
      total: "taskTotal",
      loading: "tasksLoading"
    }, message => {
      this.error = message;
    });
    this.$watch(() => this.taskPageSize, () => {
      this.taskPage = 1;
    });
    this.$watch(() => [this.taskPage, this.taskPageSize, this.appliedTaskFilters], () => {
      if (this.store.databaseReady) void this.loadTasks();
    });
    this.$watch(() => this.store.databaseReady, ready => {
      if (ready) void this.loadTasks();
    }, {
      immediate: true
    });
    bindPageActivity(this, () => {
      this.manualDisposed = false;
      this.refreshTimer = window.setInterval(() => {
        if (this.store.databaseReady && this.tasks.some(task => /执行中|进行中|策划中|生成中/.test(task.planning_status || task.status) || (task.batch_id || task.content_mode === 'marketing') && /待分配|待生产|待生成|未生成|生成中|生产中|上传中/.test(task.content_status || ''))) void this.loadTasks();
      }, 3000);
    }, () => {
      this.rememberTaskList();
      this.manualDisposed = true;
      if (this.refreshTimer !== undefined) window.clearInterval(this.refreshTimer);
    });
  }
};
</script>
<template>
<div class="vue2-component-root">
<div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
  <section ref="taskListRef" class="card manual-task-card">
    <div class="card-head"><div><h2>策划任务列表</h2></div></div>
    <form class="card-body manual-task-filter-panel" aria-label="策划任务筛选" novalidate @submit.prevent="applyTaskFilters">
      <div class="manual-task-filters query-filter-grid" data-query-filters="standard">
        <label class="field"><span>批次</span><input v-model="taskFilters.batch" type="search" placeholder="请输入" /></label>
        <DateRangeFields :start.sync="taskFilters.dateStart" :end.sync="taskFilters.dateEnd" @query="applyTaskFilters" />
        <label class="field"><span>创建人</span><input v-model="taskFilters.creator" type="search" placeholder="请输入" /></label>
        <label class="field"><span>内容状态</span><select v-model="taskFilters.contentStatus" aria-label="内容状态"><option value="">全部</option><option v-for="status in taskContentStatuses" :key="status" :value="status">{{ status === '—' ? '暂无状态' : status }}</option></select></label>
        <QueryActions @query="applyTaskFilters" @clear="taskFilters.batch=''; taskFilters.dateStart=''; taskFilters.dateEnd=''; taskFilters.creator=''; taskFilters.contentStatus=''" />
      </div>
      <p v-if="taskDateError" id="manual-task-date-error" class="inline-error" role="alert">{{ taskDateError }}</p>
    </form>
    <ManualTaskTable
      :tasks="pagedTasks"
      :loading="tasksLoading"
      :initialized="store.initialized"
      :filtered="taskFiltersActive"
      @plan-details="selectTask"
    />
    <ListPagination v-if="taskTotal" :page.sync="taskPage" :page-size.sync="taskPageSize" :total="taskTotal" unit="个任务" :page-size-options="[10, 20, 50]" class="manual-task-pagination" />
  </section>

</div>
</template>
<style scoped>

.manual-task-card .card-head{padding:20px 24px}
.manual-task-pagination{margin:14px 24px 20px}
.manual-task-card table{min-width:1220px}
.manual-task-card th{padding:13px 16px;background:var(--neutral-50);color:var(--neutral-500);font-weight:500}
.manual-task-card td{height:52px;padding:12px 16px;color:var(--neutral-600);font-size:14px;line-height:22px;font-variant-numeric:tabular-nums}
.manual-task-card tbody tr:nth-child(even){background:var(--surface)}
.manual-task-card tbody tr:hover{background:var(--hover-bg)}
.manual-task-card tbody tr.has-failures{background:var(--processing-row)}
.manual-task-card tbody tr.has-failures:hover{background:var(--processing-bg)}
.manual-task-card th:nth-child(n+3):nth-child(-n+6),.manual-task-card td:nth-child(n+3):nth-child(-n+6){text-align:center;white-space:nowrap}
.manual-task-card td:first-child{min-width:150px;max-width:220px;color:var(--neutral-700);font-weight:500;overflow-wrap:anywhere}
.manual-task-card th:last-child,.manual-task-card td:last-child{position:sticky;right:0;min-width:148px;background:var(--surface);box-shadow:-1px 0 0 var(--neutral-200)}
.manual-task-card th:last-child{z-index:2;background:var(--neutral-50)}
.manual-task-card tr:hover td:last-child{background:var(--hover-bg)}
.manual-task-card tr.has-failures td:last-child{background:var(--surface)}
.manual-task-card td:nth-child(2){white-space:nowrap}
.manual-task-card td:nth-child(9),.manual-task-card td:nth-child(10){font-size:13px;line-height:20px;color:var(--neutral-500);white-space:nowrap}
.manual-task-card .page-actions{flex-wrap:nowrap;gap:12px;white-space:nowrap}
.manual-task-card .tag{padding:3px 8px;border-radius:6px;font-size:12px;font-weight:500;white-space:nowrap}
.manual-task-card td:nth-child(8) .tag.gray{padding:0;background:transparent;color:var(--neutral-400);font-weight:400}
.manual-task-card td.manual-task-count{color:var(--neutral-400);font-size:13px;font-weight:400}
.manual-task-card td.manual-task-count.completed{color:var(--success);font-weight:600}
.manual-task-card td.manual-task-count.failed{color:var(--danger);font-weight:600}.manual-task-card .table-wrap{max-height:calc(100vh - 260px);overflow:auto}
@media(max-width:580px){.manual-task-pagination{margin-right:12px;margin-left:12px}}
.manual-task-filters > .manual-task-date-field { flex-basis: calc(var(--filter-field-width) * 2 + 12px); width: calc(var(--filter-field-width) * 2 + 12px); }
.manual-task-date-range { display: flex; align-items: center; gap: 8px; min-width: 0; width: 100%; }
.manual-task-date-range input { flex: 1 1 0; width: 0; min-width: 0; }
.manual-task-date-range > span { color: var(--neutral-400); font-size: 12px; }
@container query-filters (max-width: 640px) { .manual-task-filters > .manual-task-date-field { flex-basis: 100%; width: 100%; } }

</style>
