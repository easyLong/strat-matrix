<script lang="ts">
import QueryActions from './QueryActions.vue';
import { defineComponent, type PropType } from '../compat/composition';
import { ref, watch, onBeforeUnmount } from '../compat/composition';
import { api } from '../api';
import { usePlanningStore } from '../store';
import { useAsyncPage } from '../composables/useAsyncPage';
import ListPagination from './ListPagination.vue';
import LoadingSkeleton from './LoadingSkeleton.vue';
import PlanningExport from './PlanningExport.vue';
import AccountTypeBadge from './AccountTypeBadge.vue';
import type { AccountOption, PlanningAccountSummary } from '../types';
export default defineComponent({
    setup(props, context) {
        const emit = context.emit;
        const store = usePlanningStore();
        const initial = {
            keyword: '',
            umNo: '',
            organization: '',
            platform: '',
            lifecycle: '',
            accountType: '',
            followersMin: null as number | null,
            followersMax: null as number | null
        };
        const saved = store.resultAccountListState;
        const draft = ref(Object.assign({
            ...initial
        }, saved?.draft)), applied = ref(Object.assign({
            ...initial
        }, saved?.applied));
        const page = ref(saved?.page ?? 1), pageSize = ref(saved?.pageSize ?? 20), total = ref(0), loading = ref(false), error = ref(''), expanded = ref(true);
        const items = ref<(PlanningAccountSummary & {
            profile?: AccountOption;
        })[]>([]);
        const facets = ref({
            organizations: [] as string[],
            platforms: [] as string[],
            lifecycles: [] as string[]
        });
        const query = useAsyncPage<PlanningAccountSummary & {
            profile?: AccountOption;
        }>(async (signal) => {
            const response = await api.accountPage({
                page: page.value,
                page_size: pageSize.value,
                filters: applied.value
            }, signal);
            if (!signal.aborted)
                facets.value = response.facets;
            return response;
        }, {
            items,
            total,
            loading
        }, message => {
            error.value = message;
        });
        async function load() {
            error.value = '';
            await query.load();
            const max = Math.max(1, Math.ceil(total.value / pageSize.value));
            if (page.value > max)
                page.value = max;
        }
        function search() {
            if (draft.value.followersMin != null && draft.value.followersMax != null && draft.value.followersMin > draft.value.followersMax) {
                error.value = '粉丝量下限不能大于上限';
                return;
            }
            applied.value = {
                ...draft.value
            };
            page.value = 1;
        }
        watch([() => store.databaseReady, page, pageSize, applied], () => {
            if (store.databaseReady)
                void load();
        }, {
            immediate: true
        });
        onBeforeUnmount(() => {
            store.resultAccountListState = {
                page: page.value,
                pageSize: pageSize.value,
                draft: {
                    ...draft.value
                },
                applied: {
                    ...applied.value
                }
            };
        });
        return {
            emit,
            draft,
            applied,
            page,
            pageSize,
            total,
            loading,
            error,
            expanded,
            items,
            facets,
            search
        };
    },
    components: {QueryActions, PlanningExport, LoadingSkeleton, AccountTypeBadge, ListPagination}
});
</script>
<template>
<div class="vue2-component-root">
  <div v-if="error" class="banner error-banner" role="alert">{{error}}</div>
  <section class="card">
    <div class="card-head"><h2 class="section-title-with-icon"><span aria-hidden="true">▤</span>账号列表</h2><PlanningExport :scope="{mode:'all',page:1,page_size:200,filters:{accountFilters:applied}}" account-dates /></div>
    <form  class="card-body query-filter-grid account-query-fields" data-query-filters="standard" @submit.prevent="search">
      <label class="field"><span>生命周期</span><select v-model="draft.lifecycle"><option value="">全部</option><option v-for="x in facets.lifecycles" :key="x">{{x}}</option></select></label>
      <label class="field"><span>粉丝量</span><div class="follower-range"><input v-model.number="draft.followersMin" type="number" min="0" placeholder="起始粉丝量" /><span>至</span><input v-model.number="draft.followersMax" type="number" min="0" placeholder="截止粉丝量" /></div></label>
      <label class="field"><span>账号类型</span><select v-model="draft.accountType"><option value="">全部</option><option>认证</option><option>非认证</option></select></label>
      <label class="field"><span>属主组织</span><select v-model="draft.organization"><option value="">全部</option><option v-for="x in facets.organizations" :key="x">{{x}}</option></select></label>
      <label class="field"><span>平台</span><select v-model="draft.platform"><option value="">全部</option><option v-for="x in facets.platforms" :key="x">{{x}}</option></select></label>
      <label class="field"><span>账号 ID 或昵称</span><input v-model="draft.keyword" type="search" placeholder="请输入" /></label>
      <div class="query-filter-tail"><label class="field"><span>属主 UM 号</span><input v-model="draft.umNo" type="search" placeholder="请输入" /></label><QueryActions @query="search" @clear="draft.lifecycle=''; draft.followersMin=null; draft.followersMax=null; draft.accountType=''; draft.organization=''; draft.platform=''; draft.keyword=''; draft.umNo=''" /></div>
    </form>
    <LoadingSkeleton v-if="loading&&!items.length" />
    <div v-else class="table-wrap account-dimension-table-scroll" tabindex="0" aria-label="账号列表"><table>
      <thead><tr><th>账号</th><th>属主 UM 号</th><th>属主组织</th><th>账号类型</th><th>平台</th><th>生命周期</th><th>粉丝量</th><th>账号状态</th><th>策划结果</th></tr></thead>
      <tbody><tr v-for="item in items" :key="item.account_id"><td><div class="account-name-cell"><b>{{item.account_name}}</b><small>{{item.account_id}}</small></div></td><td>{{item.profile?.um_no||'—'}}</td><td>{{item.profile?.organization||'—'}}</td><td><AccountTypeBadge :type="item.profile?.account_type||'—'" /></td><td>{{item.profile?.platform||'—'}}</td><td>{{item.profile?.lifecycle_stage||'—'}}</td><td>{{item.profile?.followers?.toLocaleString()??'—'}}</td><td><span :class="['tag',item.profile?.status==='启用'?'green':'gray']">{{item.profile?.status||'—'}}</span></td><td><button class="text-btn" @click="emit('view-plans',item)">查看策划</button></td></tr>
        <tr v-if="!items.length"><td colspan="9" class="empty-state">暂无符合条件的账号</td></tr></tbody>
    </table></div>
    <ListPagination :page.sync="page" :page-size.sync="pageSize" :total="total" unit="个账号" class="list-pagination-inset" />
  </section>
</div>
</template>
<style scoped>
.account-query-fields{display:grid;gap:12px;align-items:end}.account-query-fields select,.account-query-fields input{height:32px;width:100%;min-width:0;box-sizing:border-box}.follower-range{display:flex;align-items:center;gap:8px}.follower-range input{width:45%}.account-dimension-table-scroll table{min-width:1120px}.account-name-cell{display:flex;flex-direction:column;gap:4px}.account-name-cell small{color:var(--neutral-400);font-size:12px}.card-head{justify-content:space-between}
</style>
