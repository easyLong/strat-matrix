<script lang="ts">
import { defineComponent, type PropType } from '../../compat/composition';
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from '../../compat/composition';
import ManualTaskTable from '../ManualTaskTable.vue';
import ListPagination from '../ListPagination.vue';
import { api } from '../../api';
import { usePlanningStore } from '../../store';
import { useAsyncPage } from '../../composables/useAsyncPage';
import { manualContentLabel, type ManualTaskFilters } from '../../ui/manualTask';
import type { ManualTaskSummary } from '../../types';
export default defineComponent({
    setup(props, context) {
        const store = usePlanningStore();
        const emit = context.emit;
        const error = ref('');
        const tasks = ref<ManualTaskSummary[]>([]);
        const taskTotal = ref(0);
        const taskListRef = ref<HTMLElement | null>(null);
        const savedTaskList = store.manualTaskListState;
        let restoreTaskListPending = Boolean(savedTaskList);
        let manualDisposed = false;
        const taskPage = ref(savedTaskList?.page ?? 1);
        const taskPageSize = ref(savedTaskList?.pageSize ?? 10);
        const taskFilters = ref<ManualTaskFilters>({
            ...(savedTaskList?.filters ?? {
                batch: '',
                dateStart: '',
                dateEnd: '',
                creator: '',
                contentStatus: ''
            })
        });
        const appliedTaskFilters = ref<ManualTaskFilters>({
            ...(savedTaskList?.appliedFilters ?? taskFilters.value)
        });
        const taskDateError = ref('');
        const taskFiltersActive = computed(() => Object.values(appliedTaskFilters.value).some(Boolean));
        const taskContentStatuses = computed(() => [...new Set(['待分配', '待生成', '生成中', '已完成', '生成失败', '部分失败', ...tasks.value.map(manualContentLabel)])]);
        const filteredTasks = computed(() => tasks.value);
        function applyTaskFilters() {
            taskDateError.value = '';
            if (taskFilters.value.dateStart && taskFilters.value.dateEnd && taskFilters.value.dateStart > taskFilters.value.dateEnd) {
                taskDateError.value = '投放开始日期不能晚于结束日期';
                return;
            }
            appliedTaskFilters.value = {
                ...taskFilters.value,
                batch: taskFilters.value.batch.trim(),
                creator: taskFilters.value.creator.trim()
            };
            taskPage.value = 1;
        }
        const tasksLoading = ref(false);
        let refreshTimer: number | undefined;
        const pagedTasks = computed(() => tasks.value);
        const taskQuery = useAsyncPage<ManualTaskSummary>(signal => api.manualTaskPage({
            page: taskPage.value,
            page_size: taskPageSize.value,
            filters: appliedTaskFilters.value
        }, signal), {
            items: tasks,
            total: taskTotal,
            loading: tasksLoading
        }, message => {
            error.value = message;
        });
        async function loadTasks() {
            const loaded = await taskQuery.load();
            if (!loaded || manualDisposed)
                return;
            error.value = '';
            const maximum = Math.max(1, Math.ceil(taskTotal.value / taskPageSize.value));
            if (taskPage.value > maximum) {
                taskPage.value = maximum;
                return;
            }
            if (restoreTaskListPending) {
                restoreTaskListPending = false;
                await nextTick();
                if (manualDisposed)
                    return;
                const table = taskListRef.value?.querySelector('.manual-task-table-wrap');
                if (table && savedTaskList) {
                    table.scrollTop = savedTaskList.tableScrollTop;
                    table.scrollLeft = savedTaskList.tableScrollLeft;
                }
                window.scrollTo({
                    top: savedTaskList?.scrollY ?? 0,
                    behavior: 'instant'
                });
            }
        }
        function rememberTaskList() {
            const table = taskListRef.value?.querySelector('.manual-task-table-wrap');
            store.manualTaskListState = {
                page: taskPage.value,
                pageSize: taskPageSize.value,
                filters: {
                    ...taskFilters.value
                },
                appliedFilters: {
                    ...appliedTaskFilters.value
                },
                scrollY: window.scrollY,
                tableScrollTop: table?.scrollTop ?? 0,
                tableScrollLeft: table?.scrollLeft ?? 0
            };
        }
        function selectTask(task: ManualTaskSummary) {
            rememberTaskList();
            emit('plan-details', task);
        }
        watch(taskPageSize, () => {
            taskPage.value = 1;
        });
        watch([taskPage, taskPageSize, appliedTaskFilters], () => {
            if (store.databaseReady)
                void loadTasks();
        });
        watch(() => store.databaseReady, ready => {
            if (ready)
                void loadTasks();
        }, {
            immediate: true
        });
        onMounted(() => {
            refreshTimer = window.setInterval(() => {
                if (store.databaseReady && tasks.value.some(task => /执行中|进行中|策划中|生成中/.test(task.planning_status || task.status) || (task.batch_id || task.content_mode === 'marketing') && /待分配|待生产|待生成|未生成|生成中|生产中|上传中/.test(task.content_status || '')))
                    void loadTasks();
            }, 3000);
        });
        onBeforeUnmount(() => {
            rememberTaskList();
            manualDisposed = true;
            if (refreshTimer !== undefined)
                window.clearInterval(refreshTimer);
        });
        return {
            store,
            error,
            taskTotal,
            taskListRef,
            taskPage,
            taskPageSize,
            taskFilters,
            taskDateError,
            taskFiltersActive,
            taskContentStatuses,
            applyTaskFilters,
            tasksLoading,
            pagedTasks,
            selectTask
        };
    },
    components: {ManualTaskTable, ListPagination}
});
</script>
<template>
<div class="vue2-component-root">
<div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
  <section ref="taskListRef" class="card manual-task-card">
    <div class="card-head"><div><h2>策划任务列表</h2></div></div>
    <form class="card-body manual-task-filter-panel" aria-label="策划任务筛选" novalidate @submit.prevent="applyTaskFilters">
      <div class="manual-task-filters query-filter-grid" data-query-filters="standard">
        <label class="field"><span>批次</span><input v-model="taskFilters.batch" type="search" placeholder="输入批次名称或批次号" /></label>
        <label class="field manual-task-date-field"><span>投放起止日期</span><div class="manual-task-date-range"><input v-model="taskFilters.dateStart" type="date" aria-label="投放开始日期" :max="taskFilters.dateEnd || undefined" :aria-invalid="!!taskDateError" :aria-describedby="taskDateError ? 'manual-task-date-error' : undefined" /><span>至</span><input v-model="taskFilters.dateEnd" type="date" aria-label="投放结束日期" :min="taskFilters.dateStart || undefined" :aria-invalid="!!taskDateError" :aria-describedby="taskDateError ? 'manual-task-date-error' : undefined" /></div></label>
        <label class="field"><span>创建人</span><input v-model="taskFilters.creator" type="search" placeholder="输入创建人" /></label>
        <label class="field"><span>内容状态</span><select v-model="taskFilters.contentStatus" aria-label="内容状态"><option value="">全部</option><option v-for="status in taskContentStatuses" :key="status" :value="status">{{ status === '—' ? '暂无状态' : status }}</option></select></label>
        <div class="query-filter-actions"><button class="btn primary" type="submit">查询</button></div>
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
