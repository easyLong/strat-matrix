<script>
import DialogTitle from '../DialogTitle.vue';
import QueryActions from '../QueryActions.vue';
import PlanOperationTimeline from './PlanOperationTimeline.vue';
import TopicDetailDrawer from '../TopicDetailDrawer.vue';
import { formatDateTime } from '../../planningTime';
import { topicLabels } from '../../topicTaxonomy';
import { canReplacePlanTopic as isReplaceable, productionStatusLabel } from '../../ui/slotContentStatus';
import { canPlanning } from '../../host/runtime';
import { api } from '../../api';
export default {
  props: {
    plan: {
      required: true,
      type: null
    }
  },
  components: {
    PlanOperationTimeline,
    DialogTitle,
    QueryActions,
    TopicDetailDrawer
  },
  data() {
    return {
      error: '',
      replaceTarget: null,
      drawerMode: 'replace',
      planTopicDetail: null,
      planDetailLoading: false,
      planOperationsLoading: false,
      planOperationsError: '',
      replacementTopics: [],
      taxonomyItems: {},
      detailTopic: null,
      replacementFiltersExpanded: true,
      replacementQuery: '',
      replacementTopicIdFilter: '',
      replacementMarketingFilter: '',
      replacementContentType: '',
      replacementProduct: '',
      replacementActivity: '',
      replacementHotspot: '',
      appliedReplacementFilters: {
        topicId: '',
        query: '',
        marketing: '',
        contentType: '',
        product: '',
        activity: '',
        hotspot: ''
      },
      replacementTopicId: '',
      replacementReason: '',
      adjustmentHistory: [],
      replaceBusy: false,
      planDetailRequest: 0,
      replacementReturnsToDetails: false,
      replacementReturnScrollTop: 0
    };
  },
  computed: {
    planDrawerBody: {
      cache: false,
      get() {
        return this.$refs.planDrawerBody || null;
      }
    },
    planTopicTagGroups() {
      if (!this.planTopicDetail) return [];
      const labels = topicLabels(this.planTopicDetail, this.taxonomyItems);
      const paths = nodes => nodes.map(node => node.path.join(' / '));
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
    },
    planOperationLogs() {
      const item = this.replaceTarget;
      if (!item) return [];
      const logs = [];
      if (item.batch_created_at) logs.push({
        key: `created-${item.id}`,
        createdAt: item.batch_created_at,
        action: '策划结果生成',
        actor: item.plan_type === 'manual' ? '人工策划' : 'AI 自动策划',
        detail: `批次 ${item.batch_code || '—'} · ${this.slotLabel(item.slot_type, item.plan_type)}`
      });
      for (const record of this.adjustmentHistory) logs.push({
        key: `adjustment-${record.id}`,
        createdAt: record.created_at,
        action: {
          manual_replace: '替换选题',
          manual: '替换选题',
          hotspot_replace: '热点定题'
        }[record.adjustment_source] || '选题调整',
        actor: record.created_by || '—',
        detail: `${record.old_topic_title || record.old_topic_id} → ${record.new_topic_title || record.new_topic_id}${record.reason ? ` · ${record.reason}` : ''}`
      });
      return logs.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    },
    replacementContentTypes() {
      return [...new Set(this.replacementTopics.map(topic => topic.content_type).filter(Boolean))].sort();
    },
    replacementProducts() {
      return [...new Set(this.replacementTopics.map(topic => topic.related_product).filter(Boolean))].sort();
    },
    replacementActivities() {
      return [...new Set(this.replacementTopics.map(topic => topic.related_activity).filter(Boolean))].sort();
    },
    replacementHotspots() {
      return [...new Set(this.replacementTopics.map(topic => topic.related_hotspot).filter(Boolean))].sort();
    },
    replacementCandidates() {
      return this.replacementTopics.filter(topic => (!this.appliedReplacementFilters.topicId.trim() || topic.topic_id === this.appliedReplacementFilters.topicId.trim()) && (!this.appliedReplacementFilters.query.trim() || topic.topic_title.toLocaleLowerCase().includes(this.appliedReplacementFilters.query.trim().toLocaleLowerCase())) && (!this.appliedReplacementFilters.marketing || String(topic.is_marketing) === this.appliedReplacementFilters.marketing) && (!this.appliedReplacementFilters.contentType || topic.content_type === this.appliedReplacementFilters.contentType) && (!this.appliedReplacementFilters.product || topic.related_product === this.appliedReplacementFilters.product) && (!this.appliedReplacementFilters.activity || topic.related_activity === this.appliedReplacementFilters.activity) && (!this.appliedReplacementFilters.hotspot || topic.related_hotspot === this.appliedReplacementFilters.hotspot));
    },
    formatDateTime() {
      return formatDateTime;
    },
    productionStatusLabel() {
      return productionStatusLabel;
    }
  },
  methods: {
    canReplacePlanTopic(item) {
      return canPlanning('results.replace') && isReplaceable(item);
    },
    slotLabel(slotType, planType) {
      if (planType === 'manual') return '手动追加';
      return {
        regular: '\u666e\u901a',
        marketing_priority: '\u8425\u9500',
        hotspot: '\u70ed\u70b9',
        manual_extra: '\u624b\u52a8\u8ffd\u52a0'
      }[slotType] ?? slotType;
    },
    topicTypeLabel(item) {
      if (!item.topic_id) return '\u5f85\u786e\u5b9a';
      const type = String(item.topic_type ?? '');
      if (type === '\u8425\u9500' || type === 'marketing' || type === 'marketing_priority') return '\u8425\u9500';
      if (type === '\u70ed\u70b9' || type === 'hotspot') return '\u70ed\u70b9';
      if (type === '\u666e\u901a' || type === 'normal' || type === 'regular') return '\u666e\u901a';
      return item.slot_type === 'hotspot' ? '\u70ed\u70b9' : item.slot_type === 'marketing_priority' ? '\u8425\u9500' : '\u666e\u901a';
    },
    weekdayLabel(date) {
      return new Intl.DateTimeFormat('zh-CN', {
        weekday: 'short',
        timeZone: 'UTC'
      }).format(new Date(`${date}T00:00:00Z`));
    },
    applyReplacementFilters() {
      this.appliedReplacementFilters = {
        topicId: this.replacementTopicIdFilter,
        query: this.replacementQuery,
        marketing: this.replacementMarketingFilter,
        contentType: this.replacementContentType,
        product: this.replacementProduct,
        activity: this.replacementActivity,
        hotspot: this.replacementHotspot
      };
    },
    async openReplacement(item) {
      if (!this.canReplacePlanTopic(item)) return;
      const request = ++this.planDetailRequest;
      this.replacementReturnsToDetails = this.drawerMode === 'view' && this.replaceTarget?.id === item.id;
      this.replacementReturnScrollTop = this.planDrawerBody?.scrollTop ?? 0;
      this.error = '';
      this.drawerMode = 'replace';
      this.replaceTarget = item;
      this.replacementFiltersExpanded = true;
      this.appliedReplacementFilters = {
        topicId: '',
        query: '',
        marketing: '',
        contentType: '',
        product: '',
        activity: '',
        hotspot: ''
      };
      this.replacementQuery = '';
      this.replacementTopicIdFilter = '';
      this.replacementMarketingFilter = '';
      this.replacementContentType = '';
      this.replacementProduct = '';
      this.replacementActivity = '';
      this.replacementHotspot = '';
      this.replacementTopicId = '';
      this.replacementReason = '';
      this.replacementTopics = [];
      this.adjustmentHistory = [];
      this.planOperationsLoading = true;
      this.planOperationsError = '';
      try {
        const [topics, history, taxonomy] = await Promise.all([api.replacementCandidates(item.id), api.adjustments(item.id), api.tagTaxonomy()]);
        if (request !== this.planDetailRequest) return;
        this.taxonomyItems = taxonomy.items;
        this.replacementTopics = topics;
        this.adjustmentHistory = history;
      } catch (exc) {
        if (request === this.planDetailRequest) this.error = exc instanceof Error ? exc.message : '读取替换信息失败';
      } finally {
        if (request === this.planDetailRequest) this.planOperationsLoading = false;
      }
    },
    async openPlanDetails(item, known) {
      const request = ++this.planDetailRequest;
      this.drawerMode = 'view';
      this.replaceTarget = item;
      this.adjustmentHistory = known?.adjustments ?? [];
      this.planOperationsError = '';
      this.planOperationsLoading = !known?.adjustments;
      const catalogTopic = known?.topic ?? null;
      this.planTopicDetail = catalogTopic ?? {
        topic_id: item.topic_id,
        topic_title: item.topic_title,
        outline: item.outline,
        content_type: item.content_type,
        category: '',
        is_marketing: item.topic_type === '营销' || item.topic_type === 'marketing',
        status: '可用',
        topic_type: this.topicTypeLabel(item) === '热点' ? '热点' : this.topicTypeLabel(item) === '营销' ? '营销' : '普通'
      };
      this.planDetailLoading = !catalogTopic && Boolean(item.topic_id);
      const [operationsResult, topicResult] = await Promise.allSettled([known?.adjustments ? Promise.resolve(known.adjustments) : api.adjustments(item.id), !catalogTopic && item.topic_id ? api.topicDetail(item.topic_id, this.topicTypeLabel(item)) : Promise.resolve(catalogTopic)]);
      if (request !== this.planDetailRequest) return;
      if (operationsResult.status === 'fulfilled') this.adjustmentHistory = operationsResult.value;else this.planOperationsError = operationsResult.reason instanceof Error ? operationsResult.reason.message : '操作记录暂不可用';
      if (topicResult.status === 'fulfilled' && topicResult.value) this.planTopicDetail = topicResult.value;else if (topicResult.status === 'rejected') this.planDetailLoading = false;
      this.planDetailLoading = false;
      this.planOperationsLoading = false;
    },
    closeReplacement() {
      this.planDetailRequest++;
      this.replaceTarget = null;
      this.planDetailLoading = false;
      this.planOperationsLoading = false;
      this.$emit('close-plan');
    },
    async confirmReplacement() {
      if (this.replaceBusy || !this.replaceTarget || !this.canReplacePlanTopic(this.replaceTarget) || !this.replacementTopicId || this.replaceTarget.result_version == null) return;
      const request = this.planDetailRequest;
      const returnToDetails = this.replacementReturnsToDetails;
      const returnScrollTop = this.replacementReturnScrollTop;
      const topic = this.replacementTopics.find(topic => topic.topic_id === this.replacementTopicId);
      this.replaceBusy = true;
      this.error = '';
      try {
        const result = await api.replaceTopic(this.replaceTarget.id, this.replacementTopicId, this.replaceTarget.result_version, this.replacementReason.trim());
        this.$emit('plan-updated', result.item);
        if (request !== this.planDetailRequest || this.replaceTarget?.id !== result.item.id || this.drawerMode !== 'replace') return;
        const adjustments = [result.adjustment, ...this.adjustmentHistory.filter(row => row.id !== result.adjustment.id)];
        this.replacementTopicId = '';
        if (returnToDetails) {
          void this.openPlanDetails(result.item, {
            topic,
            adjustments
          });
          await this.$nextTick();
          if (this.planDrawerBody) this.planDrawerBody.scrollTop = returnScrollTop;
        } else this.closeReplacement();
      } catch (exc) {
        this.error = exc instanceof Error ? exc.message : '替换失败，当前结果未改变';
      } finally {
        this.replaceBusy = false;
      }
    }
  },
  created() {
    this.$watch(() => this.plan, item => {
      void this.openPlanDetails(item);
      const request = this.planDetailRequest;
      void api.tagTaxonomy().then(taxonomy => {
        if (request === this.planDetailRequest) this.taxonomyItems = taxonomy.items;
      }).catch(() => {});
    }, {
      immediate: true
    });
  },
  beforeDestroy() {
    this.planDetailRequest++;
  }
};
</script>

<template>
<div class="vue2-component-root">
  <div v-if="replaceTarget" class="drawer-mask" @click.self="closeReplacement">
    <aside class="drawer plan-detail-drawer" role="dialog" aria-modal="true" :aria-label="drawerMode === 'view' ? String.fromCharCode(35745,21010,35814,24773) : drawerMode === 'replace' ? String.fromCharCode(26367,25442,36873,39064) : String.fromCharCode(26597,30475,35843,25972,35760,24405)">
      <div class="drawer-head"><DialogTitle :title="drawerMode === 'view' ? '计划详情' : drawerMode === 'replace' ? '替换选题' : '调整记录'" :context="replaceTarget.account_name" /><button class="icon-btn" type="button" aria-label="关闭" @click="closeReplacement">&times;</button></div>
      <div ref="planDrawerBody" class="drawer-body">

        <div v-if="error && drawerMode === 'replace'" class="banner error-banner" role="alert">{{ error }}</div>
        <template v-if="drawerMode === 'view'">
          <section class="slot-detail-section"><h3>策划信息</h3><div class="slot-detail-grid"><div><small>投放日期</small><b>{{ replaceTarget.publish_date }} · {{ weekdayLabel(replaceTarget.publish_date) }}</b></div><div><small>批次周期</small><b>{{ replaceTarget.cycle_start }} 至 {{ replaceTarget.cycle_end }}</b></div><div><small>批次编号</small><b>{{ replaceTarget.batch_code || '—' }}</b></div><div><small>策划方式</small><b>{{ replaceTarget.plan_type === 'manual' ? '人工策划' : 'AI 自动策划' }}</b></div><div><small>经营阶段</small><b>{{ replaceTarget.lifecycle_stage || '—' }}</b></div><div><small>经营作用</small><b>{{ replaceTarget.content_role || '—' }}</b></div><div><small>内容状态</small><b>{{ productionStatusLabel(replaceTarget) }}</b></div></div></section>
          <section class="slot-detail-section"><div class="slot-detail-section-head"><h3>选题信息</h3><button v-if="canReplacePlanTopic(replaceTarget)" class="btn primary" type="button" @click="openReplacement(replaceTarget)">替换选题</button></div><div v-if="planDetailLoading" class="slot-detail-loading">正在读取选题信息…</div><template v-else-if="planTopicDetail"><div class="slot-detail-grid"><div><small>选题二级分类</small><b>{{ planTopicDetail.content_type || replaceTarget.content_type || '—' }}</b></div><div><small>选题 ID</small><b>{{ planTopicDetail.topic_id || '—' }}</b></div><div class="slot-detail-wide"><small>选题标题</small><b>{{ planTopicDetail.topic_title || replaceTarget.topic_title || '—' }}</b></div><div class="slot-detail-wide"><small>选题大纲</small><b class="slot-detail-outline">{{ planTopicDetail.outline || replaceTarget.outline || '—' }}</b></div><div class="slot-detail-wide"><small>选题有效期</small><b>{{ planTopicDetail.valid_from?.slice(0, 10) || '不限' }} 至 {{ planTopicDetail.valid_to?.slice(0, 10) || '不限' }}</b></div></div><div class="slot-topic-label-groups"><div v-for="group in planTopicTagGroups" :key="group.name"><small>{{ group.name }}</small><div v-if="group.values.length" class="slot-topic-labels"><span v-for="label in group.values" :key="label">{{ label }}</span></div><b v-else class="slot-topic-label-empty">未识别</b></div></div></template><div v-else class="empty-state">暂无选题信息</div></section>
          <PlanOperationTimeline class="slot-detail-section" :logs="planOperationLogs" :loading="planOperationsLoading" :error="planOperationsError" />
        </template>
        <template v-else>
        <dl class="replacement-current-plan"><div><dt>当前选题</dt><dd>{{ replaceTarget.topic_title || '待定题' }}</dd></div><div><dt>投放日期</dt><dd>{{ replaceTarget.publish_date || '—' }}</dd></div><div><dt>策划方式</dt><dd>{{ replaceTarget.plan_type==='manual' ? '人工策划' : 'AI 自动策划' }}</dd></div><div><dt>内容状态</dt><dd>{{ productionStatusLabel(replaceTarget) }}</dd></div></dl>
        <template v-if="drawerMode === 'replace' && canReplacePlanTopic(replaceTarget)">
          <h3>选择新选题</h3>

          <div id="replacement-topic-filters"  class="replacement-topic-filters query-filter-grid" data-query-filters="narrow">
            <label class="field"><span class="field-label-with-tip">选题 ID <span class="field-help-tip" tabindex="0" title="输入完整选题 ID，进行精确匹配">?</span></span><input v-model="replacementTopicIdFilter" type="text" inputmode="text" autocomplete="off" placeholder="输入完整选题 ID" /></label>
            <label class="field"><span class="field-label-with-tip">选题标题 <span class="field-help-tip" tabindex="0" title="输入标题关键词，进行模糊搜索">?</span></span><input v-model="replacementQuery" type="search" placeholder="输入选题标题关键词" /></label>
            <label class="field"><span>选题类型</span><select v-model="replacementMarketingFilter"><option value="">全部</option><option value="true">营销</option><option value="false">非营销</option></select></label>
            <label class="field"><span>选题二级分类</span><select v-model="replacementContentType"><option value="">全部</option><option v-for="value in replacementContentTypes" :key="value" :value="value">{{ value }}</option></select></label>
            <label class="field"><span>关联产品</span><select v-model="replacementProduct"><option value="">全部</option><option v-for="value in replacementProducts" :key="value" :value="value">{{ value }}</option></select></label>
            <label class="field"><span>关联活动</span><select v-model="replacementActivity"><option value="">全部</option><option v-for="value in replacementActivities" :key="value" :value="value">{{ value }}</option></select></label>
            <div class="query-filter-tail">
                <label class="field"><span>关联属地热点</span><select v-model="replacementHotspot"><option value="">全部</option><option v-for="value in replacementHotspots" :key="value" :value="value">{{ value }}</option></select></label>
                <QueryActions @query="applyReplacementFilters" @clear="replacementTopicIdFilter = ''; replacementQuery = ''; replacementMarketingFilter = ''; replacementContentType = ''; replacementProduct = ''; replacementActivity = ''; replacementHotspot = ''" />
              </div>
          </div>
          <div class="replacement-topic-count">符合条件 {{ replacementCandidates.length }} 个选题</div>
          <div class="topic-check-list"><label v-for="topic in replacementCandidates" :key="topic.topic_id" class="topic-check"><input v-model="replacementTopicId" type="radio" :value="topic.topic_id" name="replacement-topic" /><span><button class="topic-title-link" type="button" :title="topic.topic_title" @click.prevent.stop="detailTopic = topic">{{ topic.topic_title }}</button><small class="replacement-topic-meta"><span :title="`选题 ID：${topic.topic_id}`">{{ topic.topic_id }}</span><span v-if="topic.content_type" :title="`选题二级分类：${topic.content_type}`">{{ topic.content_type }}</span><span v-if="topic.valid_to">有效至 {{ topic.valid_to.slice(0, 10) }}</span></small><small class="replacement-topic-outline" :title="topic.outline || '暂无选题大纲'"><b>选题大纲：</b>{{ topic.outline || '暂无选题大纲' }}</small></span></label></div>
          <div v-if="replacementCandidates.length === 0" class="empty-state">没有可用候选选题</div>
          <label class="field"><span>替换原因（可选）</span><select v-model="replacementReason"><option value="">请选择原因</option><option>原选题与账号不匹配</option><option>选题重复</option><option>内容方向不合适</option><option>业务临时调整</option><option>其他</option></select></label>
        </template>
        <div v-else-if="drawerMode === 'replace'" class="detail-note">{{ replaceTarget.replace_block_reason || '\u5F53\u524D\u8BB0\u5F55\u6682\u4E0D\u53EF\u66FF\u6362' }}</div>

        <PlanOperationTimeline :logs="planOperationLogs" :loading="planOperationsLoading" :error="planOperationsError" />
        </template>

      </div>
        <div v-if="drawerMode === 'replace' && canReplacePlanTopic(replaceTarget)" class="drawer-foot replacement-save-actions"><button class="btn primary" type="button" :disabled="replaceBusy || !replacementTopicId" @click="confirmReplacement">{{ replaceBusy ? '\u4fdd\u5b58\u4e2d\u2026' : '\u786e\u8ba4\u66ff\u6362' }}</button></div>
    </aside>
  </div>
  <TopicDetailDrawer v-if="detailTopic" :topic="detailTopic" :items="taxonomyItems" @close="detailTopic = null" />
</div>
</template>

<style scoped>

.topic-title-link{padding:0;border:0;background:transparent;color:var(--primary-600);font-size:13px;font-weight:500;text-align:left;line-height:1.6}.topic-title-link:hover{text-decoration:underline}.plan-detail-topic>.text-btn{float:right;font-size:12px}.replacement-topic-filters .field{width:100%}.result-filter-action-row,.replacement-filter-actions{grid-column:1/-1;display:flex;align-items:end;justify-content:flex-end;gap:8px}.slot-detail-section{margin:0 0 14px;padding:16px;border:1px solid var(--neutral-200);border-radius:10px;background:var(--surface)}.slot-detail-section>h3{margin:0 0 12px;color:var(--neutral-800);font-size:14px;line-height:20px}.slot-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px}.slot-detail-grid>div{min-width:0;padding:10px 2px;border-bottom:1px solid var(--neutral-100)}.slot-detail-grid>div:nth-last-child(-n+2){border-bottom:0}.slot-detail-grid small,.slot-topic-label-groups small{display:block;margin-bottom:5px;color:var(--neutral-400);font-size:12px}.slot-detail-grid b{display:block;color:var(--neutral-700);font-size:13px;font-weight:500;line-height:1.55;overflow-wrap:anywhere}.slot-detail-grid .slot-detail-wide{grid-column:1/-1}.slot-detail-grid .slot-detail-outline{white-space:pre-wrap}.slot-topic-label-groups{display:grid;gap:12px;margin-top:12px;padding-top:12px;border-top:1px solid var(--neutral-100)}.slot-topic-label-groups>div{display:grid;grid-template-columns:82px minmax(0,1fr);align-items:start;gap:8px}.slot-topic-label-groups small{margin:3px 0 0}.slot-topic-labels{display:flex;flex-wrap:wrap;gap:6px}.slot-topic-labels span{padding:4px 8px;border-radius:5px;background:var(--primary-50);color:var(--primary-600);font-size:12px;line-height:18px;overflow-wrap:anywhere}.slot-topic-label-empty{padding:4px 0;color:var(--neutral-400);font-size:12px;font-weight:400}.slot-detail-loading{padding:12px 0;color:var(--neutral-400);font-size:13px}.slot-operation-list{position:relative;display:grid;gap:0}.slot-operation-item{position:relative;display:grid;grid-template-columns:14px minmax(0,1fr);gap:10px;padding-bottom:16px}.slot-operation-item:not(:last-child)::before{position:absolute;top:10px;bottom:-2px;left:5px;width:1px;background:var(--neutral-200);content:''}.slot-operation-dot{z-index:1;width:11px;height:11px;margin-top:4px;border:2px solid var(--primary-200);border-radius:50%;background:var(--primary-600)}.slot-operation-content>div{display:flex;justify-content:space-between;align-items:baseline;gap:12px}.slot-operation-content b{color:var(--neutral-700);font-size:13px}.slot-operation-content time,.slot-operation-content small{color:var(--neutral-400);font-size:11px}.slot-operation-content p{margin:5px 0;color:var(--neutral-600);font-size:12px;line-height:1.6;overflow-wrap:anywhere}.slot-operation-content small{display:block}@media(max-width:580px){.slot-detail-grid{grid-template-columns:1fr}.slot-detail-grid>div:nth-last-child(-n+2){border-bottom:1px solid var(--neutral-100)}.slot-detail-grid>div:last-child{border-bottom:0}.slot-detail-grid .slot-detail-wide{grid-column:auto}.slot-topic-label-groups>div{grid-template-columns:72px minmax(0,1fr)}.slot-operation-content>div{align-items:flex-start;flex-direction:column;gap:3px}}


.slot-detail-section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.slot-detail-section-head h3{margin:0;color:var(--neutral-800);font-size:14px;line-height:20px}.slot-detail-section-head .btn{flex:none}

</style>
