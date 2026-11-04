<script lang="ts">
import { defineComponent, type PropType } from '../../compat/composition';
import { computed, nextTick, ref, watch, onBeforeUnmount } from '../../compat/composition';
import TopicDetailDrawer from '../TopicDetailDrawer.vue';
import PageBreadcrumbs from '../PageBreadcrumbs.vue';
import { formatDateTime } from '../../planningTime';
import { topicLabels, type TaxonomyItems } from '../../topicTaxonomy';
import { canReplacePlanTopic, productionStatusLabel } from '../../ui/slotContentStatus';
import { api } from '../../api';
import type { AccountPlanRecord, AdjustmentRecord, TopicOption } from '../../types';
import { usePageBreadcrumbs } from '../../composables/usePageBreadcrumbs';
type SlotOperationLog = {
    key: string;
    createdAt: string;
    action: string;
    actor: string;
    detail: string;
};
export default defineComponent({
    props: { plan: { required: true, type: null as unknown as PropType<AccountPlanRecord> } },
    setup(props, context) {
        const emit = context.emit;
        const error = ref('');
        const replaceTarget = ref<AccountPlanRecord | null>(null);
        const planDrawerBody = ref<HTMLElement | null>(null);
        const drawerMode = ref<'view' | 'replace' | 'history'>('replace');
        const planTopicDetail = ref<TopicOption | null>(null);
        const planDetailLoading = ref(false);
        const planOperationsLoading = ref(false);
        const planOperationsError = ref('');
        const replacementTopics = ref<TopicOption[]>([]);
        const taxonomyItems = ref<TaxonomyItems>({});
        const detailTopic = ref<TopicOption | null>(null);
        const replacementFiltersExpanded = ref(true);
        const replacementQuery = ref('');
        const replacementTopicIdFilter = ref('');
        const replacementMarketingFilter = ref('');
        const replacementContentType = ref('');
        const replacementProduct = ref('');
        const replacementActivity = ref('');
        const replacementHotspot = ref('');
        const appliedReplacementFilters = ref({
            topicId: '',
            query: '',
            marketing: '',
            contentType: '',
            product: '',
            activity: '',
            hotspot: ''
        });
        const replacementTopicId = ref('');
        const replacementReason = ref('');
        const adjustmentHistory = ref<AdjustmentRecord[]>([]);
        const replaceBusy = ref(false);
        let planDetailRequest = 0;
        let replacementReturnsToDetails = false;
        let replacementReturnScrollTop = 0;
        const planTopicTagGroups = computed(() => {
            if (!planTopicDetail.value)
                return [];
            const labels = topicLabels(planTopicDetail.value, taxonomyItems.value);
            const paths = (nodes: {
                name: string;
                path: string[];
            }[]) => nodes.map(node => node.path.join(' / '));
            return [{
                    name: '业务属性',
                    values: [labels.business]
                }, {
                    name: '经营作用',
                    values: [labels.role]
                }, {
                    name: '内容主题',
                    values: paths([...(labels.primary ? [labels.primary] : []), ...labels.related])
                }, {
                    name: '目标客群',
                    values: paths(labels.audience)
                }, {
                    name: '使用场景',
                    values: paths(labels.scenes)
                }, {
                    name: '用户需求',
                    values: [labels.need]
                }].map(group => ({
                ...group,
                values: group.values.filter(Boolean)
            }));
        });
        const planOperationLogs = computed<SlotOperationLog[]>(() => {
            const item = replaceTarget.value;
            if (!item)
                return [];
            const logs: SlotOperationLog[] = [];
            if (item.batch_created_at)
                logs.push({
                    key: `created-${item.id}`,
                    createdAt: item.batch_created_at,
                    action: '策划结果生成',
                    actor: item.plan_type === 'manual' ? '人工策划' : 'AI 自动策划',
                    detail: `批次 ${item.batch_code || '—'} · ${slotLabel(item.slot_type, item.plan_type)}`
                });
            for (const record of adjustmentHistory.value)
                logs.push({
                    key: `adjustment-${record.id}`,
                    createdAt: record.created_at,
                    action: record.adjustment_source || '选题调整',
                    actor: record.created_by || '—',
                    detail: `${record.old_topic_title || record.old_topic_id} → ${record.new_topic_title || record.new_topic_id}${record.reason ? ` · ${record.reason}` : ''}`
                });
            return logs.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
        });
        function slotLabel(slotType: string, planType: string) {
            if (planType === 'manual')
                return '手动追加';
            return ({
                regular: '\u666e\u901a',
                marketing_priority: '\u8425\u9500',
                hotspot: '\u70ed\u70b9',
                manual_extra: '\u624b\u52a8\u8ffd\u52a0'
            } as Record<string, string>)[slotType] ?? slotType;
        }
        function topicTypeLabel(item: AccountPlanRecord) {
            if (!item.topic_id)
                return '\u5f85\u786e\u5b9a';
            const type = String(item.topic_type ?? '');
            if (type === '\u8425\u9500' || type === 'marketing' || type === 'marketing_priority')
                return '\u8425\u9500';
            if (type === '\u70ed\u70b9' || type === 'hotspot')
                return '\u70ed\u70b9';
            if (type === '\u666e\u901a' || type === 'normal' || type === 'regular')
                return '\u666e\u901a';
            return item.slot_type === 'hotspot' ? '\u70ed\u70b9' : item.slot_type === 'marketing_priority' ? '\u8425\u9500' : '\u666e\u901a';
        }
        function weekdayLabel(date: string) {
            return new Intl.DateTimeFormat('zh-CN', {
                weekday: 'short',
                timeZone: 'UTC'
            }).format(new Date(`${date}T00:00:00Z`));
        }
        const replacementContentTypes = computed(() => [...new Set(replacementTopics.value.map(topic => topic.content_type).filter(Boolean))].sort());
        const replacementProducts = computed(() => [...new Set(replacementTopics.value.map(topic => topic.related_product).filter(Boolean))].sort());
        const replacementActivities = computed(() => [...new Set(replacementTopics.value.map(topic => topic.related_activity).filter(Boolean))].sort());
        const replacementHotspots = computed(() => [...new Set(replacementTopics.value.map(topic => topic.related_hotspot).filter(Boolean))].sort());
        const replacementCandidates = computed(() => replacementTopics.value.filter(topic => (!appliedReplacementFilters.value.topicId.trim() || topic.topic_id === appliedReplacementFilters.value.topicId.trim()) && (!appliedReplacementFilters.value.query.trim() || topic.topic_title.toLocaleLowerCase().includes(appliedReplacementFilters.value.query.trim().toLocaleLowerCase())) && (!appliedReplacementFilters.value.marketing || String(topic.is_marketing) === appliedReplacementFilters.value.marketing) && (!appliedReplacementFilters.value.contentType || topic.content_type === appliedReplacementFilters.value.contentType) && (!appliedReplacementFilters.value.product || topic.related_product === appliedReplacementFilters.value.product) && (!appliedReplacementFilters.value.activity || topic.related_activity === appliedReplacementFilters.value.activity) && (!appliedReplacementFilters.value.hotspot || topic.related_hotspot === appliedReplacementFilters.value.hotspot)));
        function applyReplacementFilters() {
            appliedReplacementFilters.value = {
                topicId: replacementTopicIdFilter.value,
                query: replacementQuery.value,
                marketing: replacementMarketingFilter.value,
                contentType: replacementContentType.value,
                product: replacementProduct.value,
                activity: replacementActivity.value,
                hotspot: replacementHotspot.value
            };
        }
        async function openReplacement(item: AccountPlanRecord) {
            if (!canReplacePlanTopic(item))
                return;
            const request = ++planDetailRequest;
            replacementReturnsToDetails = drawerMode.value === 'view' && replaceTarget.value?.id === item.id;
            replacementReturnScrollTop = planDrawerBody.value?.scrollTop ?? 0;
            error.value = '';
            drawerMode.value = 'replace';
            replaceTarget.value = item;
            replacementFiltersExpanded.value = true;
            appliedReplacementFilters.value = {
                topicId: '',
                query: '',
                marketing: '',
                contentType: '',
                product: '',
                activity: '',
                hotspot: ''
            };
            replacementQuery.value = '';
            replacementTopicIdFilter.value = '';
            replacementMarketingFilter.value = '';
            replacementContentType.value = '';
            replacementProduct.value = '';
            replacementActivity.value = '';
            replacementHotspot.value = '';
            replacementTopicId.value = '';
            replacementReason.value = '';
            replacementTopics.value = [];
            adjustmentHistory.value = [];
            try {
                const [topics, history, taxonomy] = await Promise.all([api.replacementCandidates(item.id), api.adjustments(item.id), api.tagTaxonomy()]);
                if (request !== planDetailRequest)
                    return;
                taxonomyItems.value = taxonomy.items;
                replacementTopics.value = topics;
                adjustmentHistory.value = history;
            }
            catch (exc) {
                if (request === planDetailRequest)
                    error.value = exc instanceof Error ? exc.message : '读取替换信息失败';
            }
        }
        async function openPlanDetails(item: AccountPlanRecord, known?: {
            topic?: TopicOption;
            adjustments?: AdjustmentRecord[];
        }) {
            const request = ++planDetailRequest;
            drawerMode.value = 'view';
            replaceTarget.value = item;
            adjustmentHistory.value = known?.adjustments ?? [];
            planOperationsError.value = '';
            planOperationsLoading.value = !known?.adjustments;
            const catalogTopic = known?.topic ?? null;
            planTopicDetail.value = catalogTopic ?? {
                topic_id: item.topic_id,
                topic_title: item.topic_title,
                outline: item.outline,
                content_type: item.content_type,
                category: '',
                is_marketing: item.topic_type === '营销' || item.topic_type === 'marketing',
                status: '可用',
                topic_type: topicTypeLabel(item) === '热点' ? '热点' : topicTypeLabel(item) === '营销' ? '营销' : '普通'
            };
            planDetailLoading.value = !catalogTopic && Boolean(item.topic_id);
            const [operationsResult, topicResult] = await Promise.allSettled([known?.adjustments ? Promise.resolve(known.adjustments) : api.adjustments(item.id), !catalogTopic && item.topic_id ? api.topicDetail(item.topic_id, topicTypeLabel(item)) : Promise.resolve(catalogTopic)]);
            if (request !== planDetailRequest)
                return;
            if (operationsResult.status === 'fulfilled')
                adjustmentHistory.value = operationsResult.value;
            else
                planOperationsError.value = operationsResult.reason instanceof Error ? operationsResult.reason.message : '操作记录暂不可用';
            if (topicResult.status === 'fulfilled' && topicResult.value)
                planTopicDetail.value = topicResult.value;
            else if (topicResult.status === 'rejected')
                planDetailLoading.value = false;
            planDetailLoading.value = false;
            planOperationsLoading.value = false;
        }
        function closeReplacement() {
            planDetailRequest++;
            replaceTarget.value = null;
            planDetailLoading.value = false;
            planOperationsLoading.value = false;
            emit('close-plan');
        }
        async function confirmReplacement() {
            if (replaceBusy.value || !replaceTarget.value || !canReplacePlanTopic(replaceTarget.value) || !replacementTopicId.value || replaceTarget.value.result_version == null)
                return;
            const request = planDetailRequest;
            const returnToDetails = replacementReturnsToDetails;
            const returnScrollTop = replacementReturnScrollTop;
            const topic = replacementTopics.value.find(topic => topic.topic_id === replacementTopicId.value);
            replaceBusy.value = true;
            error.value = '';
            try {
                const result = await api.replaceTopic(replaceTarget.value.id, replacementTopicId.value, replaceTarget.value.result_version, replacementReason.value.trim());
                emit('plan-updated', result.item);
                if (request !== planDetailRequest || replaceTarget.value?.id !== result.item.id || drawerMode.value !== 'replace')
                    return;
                const adjustments = [result.adjustment, ...adjustmentHistory.value.filter(row => row.id !== result.adjustment.id)];
                replacementTopicId.value = '';
                if (returnToDetails) {
                    void openPlanDetails(result.item, {
                        topic,
                        adjustments
                    });
                    await nextTick();
                    if (planDrawerBody.value)
                        planDrawerBody.value.scrollTop = returnScrollTop;
                }
                else
                    closeReplacement();
            }
            catch (exc) {
                error.value = exc instanceof Error ? exc.message : '替换失败，当前结果未改变';
            }
            finally {
                replaceBusy.value = false;
            }
        }
        usePageBreadcrumbs(() => {
            if (!replaceTarget.value)
                return [];
            const plan = {
                label: '计划详情',
                action: async () => {
                    if (replaceBusy.value || !replaceTarget.value)
                        return;
                    await openPlanDetails(replaceTarget.value);
                }
            };
            if (drawerMode.value === 'replace')
                return [plan, {
                        label: '替换选题'
                    }];
            if (drawerMode.value === 'history')
                return [plan, {
                        label: '调整记录'
                    }];
            return [plan];
        }, {
            append: true,
            close: closeReplacement
        });
        watch(() => props.plan, item => {
            void openPlanDetails(item);
            const request = planDetailRequest;
            void api.tagTaxonomy().then(taxonomy => {
                if (request === planDetailRequest)
                    taxonomyItems.value = taxonomy.items;
            }).catch(() => { });
        }, {
            immediate: true
        });
        onBeforeUnmount(() => {
            planDetailRequest++;
        });
        return {
            formatDateTime,
            canReplacePlanTopic,
            productionStatusLabel,
            error,
            replaceTarget,
            planDrawerBody,
            drawerMode,
            planTopicDetail,
            planDetailLoading,
            planOperationsLoading,
            planOperationsError,
            taxonomyItems,
            detailTopic,
            replacementFiltersExpanded,
            replacementQuery,
            replacementTopicIdFilter,
            replacementMarketingFilter,
            replacementContentType,
            replacementProduct,
            replacementActivity,
            replacementHotspot,
            replacementTopicId,
            replacementReason,
            adjustmentHistory,
            replaceBusy,
            planTopicTagGroups,
            planOperationLogs,
            slotLabel,
            weekdayLabel,
            replacementContentTypes,
            replacementProducts,
            replacementActivities,
            replacementHotspots,
            replacementCandidates,
            applyReplacementFilters,
            openReplacement,
            closeReplacement,
            confirmReplacement
        };
    },
    components: {PageBreadcrumbs, TopicDetailDrawer}
});
</script>

<template>
<div class="vue2-component-root">
  <div v-if="replaceTarget" class="drawer-mask" @click.self="closeReplacement">
    <aside class="drawer" role="dialog" aria-modal="true" :aria-label="drawerMode === 'view' ? String.fromCharCode(35745,21010,35814,24773) : drawerMode === 'replace' ? String.fromCharCode(26367,25442,36873,39064) : String.fromCharCode(26597,30475,35843,25972,35760,24405)">
      <div class="drawer-head"><div><small>{{ drawerMode === 'view' ? String.fromCharCode(35745,21010,35814,24773) : drawerMode === 'replace' ? String.fromCharCode(26367,25442,36873,39064) : String.fromCharCode(26597,30475,35843,25972,35760,24405) }}</small><h2>{{ replaceTarget.account_name }}</h2></div><button class="icon-btn" type="button" aria-label="关闭" @click="closeReplacement">&times;</button></div>
      <div ref="planDrawerBody" class="drawer-body">
        <PageBreadcrumbs compact />
        <div v-if="error && drawerMode === 'replace'" class="banner error-banner" role="alert">{{ error }}</div>
        <template v-if="drawerMode === 'view'">
          <section class="slot-detail-section"><h3>策划信息</h3><div class="slot-detail-grid"><div><small>投放日期</small><b>{{ replaceTarget.publish_date }} · {{ weekdayLabel(replaceTarget.publish_date) }}</b></div><div><small>批次周期</small><b>{{ replaceTarget.cycle_start }} 至 {{ replaceTarget.cycle_end }}</b></div><div><small>批次编号</small><b>{{ replaceTarget.batch_code || '—' }}</b></div><div><small>策划方式</small><b>{{ replaceTarget.plan_type === 'manual' ? '人工策划' : 'AI 自动策划' }}</b></div><div><small>经营阶段</small><b>{{ replaceTarget.lifecycle_stage || '—' }}</b></div><div><small>经营作用</small><b>{{ replaceTarget.content_role || '—' }}</b></div><div><small>内容状态</small><b>{{ productionStatusLabel(replaceTarget) }}</b></div></div></section>
          <section class="slot-detail-section"><div class="slot-detail-section-head"><h3>选题信息</h3><button v-if="canReplacePlanTopic(replaceTarget)" class="btn primary" type="button" @click="openReplacement(replaceTarget)">替换选题</button></div><div v-if="planDetailLoading" class="slot-detail-loading">正在读取选题信息…</div><template v-else-if="planTopicDetail"><div class="slot-detail-grid"><div><small>选题二级分类</small><b>{{ planTopicDetail.content_type || replaceTarget.content_type || '—' }}</b></div><div><small>选题 ID</small><b>{{ planTopicDetail.topic_id || '—' }}</b></div><div class="slot-detail-wide"><small>选题标题</small><b>{{ planTopicDetail.topic_title || replaceTarget.topic_title || '—' }}</b></div><div class="slot-detail-wide"><small>选题大纲</small><b class="slot-detail-outline">{{ planTopicDetail.outline || replaceTarget.outline || '—' }}</b></div><div class="slot-detail-wide"><small>选题有效期</small><b>{{ planTopicDetail.valid_from?.slice(0, 10) || '不限' }} 至 {{ planTopicDetail.valid_to?.slice(0, 10) || '不限' }}</b></div></div><div class="slot-topic-label-groups"><div v-for="group in planTopicTagGroups" :key="group.name"><small>{{ group.name }}</small><div v-if="group.values.length" class="slot-topic-labels"><span v-for="label in group.values" :key="label">{{ label }}</span></div><b v-else class="slot-topic-label-empty">未识别</b></div></div></template><div v-else class="empty-state">暂无选题信息</div></section>
          <section class="slot-detail-section"><h3>操作记录</h3><div v-if="planOperationsLoading" class="slot-detail-loading">正在读取操作记录…</div><div v-else-if="planOperationsError" class="detail-note" role="alert">{{ planOperationsError }}</div><div v-else-if="planOperationLogs.length" class="slot-operation-list"><article v-for="log in planOperationLogs" :key="log.key" class="slot-operation-item"><span class="slot-operation-dot" aria-hidden="true"/><div class="slot-operation-content"><div><b>{{ log.action }}</b><time>{{ formatDateTime(log.createdAt) }}</time></div><p>{{ log.detail }}</p><small>操作方：{{ log.actor }}</small></div></article></div><div v-else class="empty-state">暂无操作记录</div></section>
        </template>
        <template v-else>
        <div class="detail-note"><b>当前选题:</b>{{ replaceTarget.topic_title }}<br /><b>投放日期:</b>{{ replaceTarget.publish_date }}<br /><b>类型:</b>{{ slotLabel(replaceTarget.slot_type, replaceTarget.plan_type) }}<br /><b>状态:</b>{{ replaceTarget.publish_status }}</div>
        <template v-if="drawerMode === 'replace' && canReplacePlanTopic(replaceTarget)">
          <h3>选择新选题</h3>
          <div class="replacement-filter-collapse-row"><button class="filter-collapse-toggle" type="button" aria-controls="replacement-topic-filters" :aria-expanded="replacementFiltersExpanded" @click="replacementFiltersExpanded = !replacementFiltersExpanded"><span>筛选条件</span><svg :class="{ expanded: replacementFiltersExpanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg></button></div>
          <div id="replacement-topic-filters" v-show="replacementFiltersExpanded" class="replacement-topic-filters query-filter-grid" data-query-filters="narrow">
            <label class="field"><span class="field-label-with-tip">选题 ID <span class="field-help-tip" tabindex="0" title="输入完整选题 ID，进行精确匹配">?</span></span><input v-model="replacementTopicIdFilter" type="text" inputmode="text" autocomplete="off" placeholder="输入完整选题 ID" /></label>
            <label class="field"><span class="field-label-with-tip">选题标题 <span class="field-help-tip" tabindex="0" title="输入标题关键词，进行模糊搜索">?</span></span><input v-model="replacementQuery" type="search" placeholder="输入选题标题关键词" /></label>
            <label class="field"><span>选题类型</span><select v-model="replacementMarketingFilter"><option value="">全部</option><option value="true">营销</option><option value="false">非营销</option></select></label>
            <label class="field"><span>选题二级分类</span><select v-model="replacementContentType"><option value="">全部</option><option v-for="value in replacementContentTypes" :key="value" :value="value">{{ value }}</option></select></label>
            <label class="field"><span>关联产品</span><select v-model="replacementProduct"><option value="">全部</option><option v-for="value in replacementProducts" :key="value" :value="value">{{ value }}</option></select></label>
            <label class="field"><span>关联活动</span><select v-model="replacementActivity"><option value="">全部</option><option v-for="value in replacementActivities" :key="value" :value="value">{{ value }}</option></select></label>
            <div class="query-filter-tail">
                <label class="field"><span>关联属地热点</span><select v-model="replacementHotspot"><option value="">全部</option><option v-for="value in replacementHotspots" :key="value" :value="value">{{ value }}</option></select></label>
                <div class="replacement-filter-actions query-filter-actions"><button class="text-btn replacement-filter-clear" type="button" @click="replacementTopicIdFilter = ''; replacementQuery = ''; replacementMarketingFilter = ''; replacementContentType = ''; replacementProduct = ''; replacementActivity = ''; replacementHotspot = ''">清空筛选</button><button class="btn primary" type="button" @click="applyReplacementFilters">查询</button></div>
              </div>
          </div>
          <div class="replacement-topic-count">符合条件 {{ replacementCandidates.length }} 个选题</div>
          <div class="topic-check-list"><label v-for="topic in replacementCandidates" :key="topic.topic_id" class="topic-check"><input v-model="replacementTopicId" type="radio" :value="topic.topic_id" name="replacement-topic" /><span><button class="topic-title-link" type="button" @click.prevent.stop="detailTopic = topic">{{ topic.topic_title }}</button><small>{{ topic.topic_id }}<template v-if="topic.content_type"> · {{ topic.content_type }}</template><template v-if="topic.valid_to"> · 有效至 {{ topic.valid_to.slice(0, 10) }}</template></small><small class="replacement-topic-outline"><b>选题大纲</b>{{ topic.outline || '暂无选题大纲' }}</small></span></label></div>
          <div v-if="replacementCandidates.length === 0" class="empty-state">没有可用候选选题</div>
          <label class="field"><span>替换原因（可选）</span><select v-model="replacementReason"><option value="">请选择原因</option><option>原选题与账号不匹配</option><option>选题重复</option><option>内容方向不合适</option><option>业务临时调整</option><option>其他</option></select></label>
        </template>
        <div v-else-if="drawerMode === 'replace'" class="detail-note">{{ replaceTarget.replace_block_reason || '\u5F53\u524D\u8BB0\u5F55\u6682\u4E0D\u53EF\u66FF\u6362' }}</div>

        <h3>调整记录</h3>
        <div v-if="adjustmentHistory.length === 0" class="empty-state">暂无历史调整</div>
        <div v-for="record in adjustmentHistory" :key="record.id" class="detail-note">{{ formatDateTime(record.created_at) }} · {{ record.created_by }} · {{ record.adjustment_source }}<br />{{ record.old_topic_title }} · {{ record.new_topic_title }}<span v-if="record.reason"> · {{ record.reason }}</span></div>
        </template>
        <div v-if="drawerMode === 'replace' && canReplacePlanTopic(replaceTarget)" class="footer-actions"><button class="btn primary" type="button" :disabled="replaceBusy || !replacementTopicId" @click="confirmReplacement">{{ replaceBusy ? '\u4fdd\u5b58\u4e2d\u2026' : '\u786e\u8ba4\u66ff\u6362' }}</button></div>
      </div>
    </aside>
  </div>
  <TopicDetailDrawer v-if="detailTopic" :topic="detailTopic" :items="taxonomyItems" @close="detailTopic = null" />
</div>
</template>

<style scoped>

.topic-title-link{padding:0;border:0;background:transparent;color:var(--primary-600);font-size:13px;font-weight:500;text-align:left;line-height:1.6}.topic-title-link:hover{text-decoration:underline}.plan-detail-topic>.text-btn{float:right;font-size:12px}.replacement-topic-filters .field{width:100%}.result-filter-action-row,.replacement-filter-actions{grid-column:1/-1;display:flex;align-items:end;justify-content:flex-end;gap:8px}.slot-detail-section{margin:0 0 14px;padding:16px;border:1px solid var(--neutral-200);border-radius:10px;background:var(--surface)}.slot-detail-section>h3{margin:0 0 12px;color:var(--neutral-800);font-size:14px;line-height:20px}.slot-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px}.slot-detail-grid>div{min-width:0;padding:10px 2px;border-bottom:1px solid var(--neutral-100)}.slot-detail-grid>div:nth-last-child(-n+2){border-bottom:0}.slot-detail-grid small,.slot-topic-label-groups small{display:block;margin-bottom:5px;color:var(--neutral-400);font-size:12px}.slot-detail-grid b{display:block;color:var(--neutral-700);font-size:13px;font-weight:500;line-height:1.55;overflow-wrap:anywhere}.slot-detail-grid .slot-detail-wide{grid-column:1/-1}.slot-detail-grid .slot-detail-outline{white-space:pre-wrap}.slot-topic-label-groups{display:grid;gap:12px;margin-top:12px;padding-top:12px;border-top:1px solid var(--neutral-100)}.slot-topic-label-groups>div{display:grid;grid-template-columns:82px minmax(0,1fr);align-items:start;gap:8px}.slot-topic-label-groups small{margin:3px 0 0}.slot-topic-labels{display:flex;flex-wrap:wrap;gap:6px}.slot-topic-labels span{padding:4px 8px;border-radius:5px;background:var(--primary-50);color:var(--primary-600);font-size:12px;line-height:18px;overflow-wrap:anywhere}.slot-topic-label-empty{padding:4px 0;color:var(--neutral-400);font-size:12px;font-weight:400}.slot-detail-loading{padding:12px 0;color:var(--neutral-400);font-size:13px}.slot-operation-list{position:relative;display:grid;gap:0}.slot-operation-item{position:relative;display:grid;grid-template-columns:14px minmax(0,1fr);gap:10px;padding-bottom:16px}.slot-operation-item:not(:last-child)::before{position:absolute;top:10px;bottom:-2px;left:5px;width:1px;background:var(--neutral-200);content:''}.slot-operation-dot{z-index:1;width:11px;height:11px;margin-top:4px;border:2px solid var(--primary-200);border-radius:50%;background:var(--primary-600)}.slot-operation-content>div{display:flex;justify-content:space-between;align-items:baseline;gap:12px}.slot-operation-content b{color:var(--neutral-700);font-size:13px}.slot-operation-content time,.slot-operation-content small{color:var(--neutral-400);font-size:11px}.slot-operation-content p{margin:5px 0;color:var(--neutral-600);font-size:12px;line-height:1.6;overflow-wrap:anywhere}.slot-operation-content small{display:block}@media(max-width:580px){.slot-detail-grid{grid-template-columns:1fr}.slot-detail-grid>div:nth-last-child(-n+2){border-bottom:1px solid var(--neutral-100)}.slot-detail-grid>div:last-child{border-bottom:0}.slot-detail-grid .slot-detail-wide{grid-column:auto}.slot-topic-label-groups>div{grid-template-columns:72px minmax(0,1fr)}.slot-operation-content>div{align-items:flex-start;flex-direction:column;gap:3px}}


.slot-detail-section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.slot-detail-section-head h3{margin:0;color:var(--neutral-800);font-size:14px;line-height:20px}.slot-detail-section-head .btn{flex:none}

</style>
