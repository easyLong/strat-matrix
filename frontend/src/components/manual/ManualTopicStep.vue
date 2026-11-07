<script lang="ts">
import { defineComponent, type PropType } from '../../compat/composition';
import { computed, toRef } from '../../compat/composition';
import HoverHint from '../HoverHint.vue';
import ListPagination from '../ListPagination.vue';
import LoadingSkeleton from '../LoadingSkeleton.vue';
import MarketingTopicTable from '../MarketingTopicTable.vue';
import { marketingTopicName, topicValidityLabel } from '../../ui/manualTopics';
import type { ManualTopicSelection } from '../../composables/useManualTopicSelection';
export default defineComponent({
    props: { selection: { required: true, type: null as unknown as PropType<ManualTopicSelection> },
        marketing: { required: true, type: Boolean as PropType<boolean> },
        loading: { required: true, type: Boolean as PropType<boolean> },
        initialized: { required: true, type: Boolean as PropType<boolean> },
        review: { required: true, type: Boolean as PropType<boolean> },
        allocationCount: { required: true, type: [Number, String] as PropType<number | ''> } },
    setup(props, context) {
        const isMarketing = toRef(props, 'marketing');
        const topicReview = computed({
            get: () => props.review,
            set: value => emit('update:review', value)
        });
        const allocationCountModel = computed({
            get: () => props.allocationCount,
            set: value => emit('update:allocationCount', value)
        });
        const emit = context.emit;
        const { topicListRef, topicFiltersExpanded, selectedTopicIds, topicIdFilter, topicQuery, topicTypeFilter, contentType, relatedProduct, relatedActivity, relatedHotspot, appliedTopicFilters, topicPage, topicPageSize, contentTypes, relatedProducts, relatedActivities, relatedHotspots, filteredTopics, topicPageCount, pagedTopics, applyTopicFilters, toggleTopicRow, setTopicSelected, removeTopic, topicTooltip, selectedTopics, validityHint } = props.selection;
        return {
            isMarketing,
            validityHint,
            marketingTopicName,
            topicValidityLabel,
            topicReview,
            allocationCountModel,
            emit,
            topicListRef,
            topicFiltersExpanded,
            selectedTopicIds,
            topicIdFilter,
            topicQuery,
            topicTypeFilter,
            contentType,
            relatedProduct,
            relatedActivity,
            relatedHotspot,
            topicPage,
            topicPageSize,
            contentTypes,
            relatedProducts,
            relatedActivities,
            relatedHotspots,
            filteredTopics,
            pagedTopics,
            applyTopicFilters,
            toggleTopicRow,
            setTopicSelected,
            removeTopic,
            topicTooltip,
            selectedTopics
        };
    },
    components: {LoadingSkeleton, HoverHint, ListPagination, MarketingTopicTable}
});
</script>
<template>
    <section key="manual-step-topics" class="manual-topic-step" :class="{ card: !isMarketing, 'manual-marketing-topic-step': isMarketing }">
      <div v-if="!isMarketing" class="card-head"><div><h2>选择选题</h2></div><span class="manual-selected-count">已选 {{ selectedTopicIds.length }} 个</span></div>
      <div class="manual-step-body" :class="{ 'card-body': !isMarketing }">
        <section class="manual-topic-selection-section" :class="{ card: isMarketing }" :aria-label="isMarketing ? '选择选题' : undefined">
          <div v-if="isMarketing" class="card-head manual-topic-substep-head"><h2><span class="manual-topic-substep-number" aria-hidden="true">1</span>选择选题</h2><span class="manual-selected-count">已选 {{ selectedTopicIds.length }} 个</span></div>
          <div :class="{ 'card-body': isMarketing }">
        <div :class="['manual-topic-picker', { 'single-topic-picker': isMarketing }]">
          <aside v-if="!isMarketing" class="manual-topic-picked">
            <div class="manual-topic-picked-head"><b>已选选题</b><span>{{ selectedTopics.length }}</span></div>
            <div v-if="selectedTopics.length" class="manual-topic-picked-list">
              <article v-for="(topic, index) in selectedTopics" :key="`${index}-${topic.topic_id}`" class="manual-topic-picked-item" tabindex="0" :title="topicTooltip(topic)"><div><small>{{ topic.topic_id }}</small><b>{{ topic.topic_title }}</b><p>{{ topic.outline || '\u6682\u65e0\u9009\u9898\u5927\u7eb2' }}</p><small>{{ topic.content_type || '\u2014' }}</small></div><button class="remove-topic" type="button" :disabled="topicReview" aria-label="移除选题" @click="removeTopic(index)">×</button></article>
            </div>
            <div v-else class="manual-topic-picked-empty">{{ isMarketing ? '请选择一个选题' : '请从右侧选题库添加' }}</div>
          </aside>
          <section class="manual-topic-picker-available">
            <div class="topic-filters-toggle"><button class="filter-collapse-toggle" type="button" :aria-expanded="topicFiltersExpanded" aria-controls="manual-topic-filters" @click="topicFiltersExpanded = !topicFiltersExpanded">筛选条件 <span>{{ topicFiltersExpanded ? '\u2303' : '\u2304' }}</span></button></div>
            <fieldset :disabled="topicReview" id="manual-topic-filters" v-show="topicFiltersExpanded" class="manual-topic-filters query-filter-grid" data-query-filters="standard">
              <label class="field"><span class="field-label-with-tip">选题 ID <span class="field-help-tip" tabindex="0" title="输入完整选题 ID;进行精确匹配">?</span></span><input v-model="topicIdFilter" type="text" inputmode="text" autocomplete="off" placeholder="输入完整选题 ID" /></label>
              <label class="field"><span class="field-label-with-tip">{{ isMarketing ? '活动／产品名称' : '选题标题' }} <span class="field-help-tip" tabindex="0" :title="isMarketing ? '输入活动或产品名称关键词进行模糊搜索' : '输入标题关键词进行模糊搜索'">?</span></span><input v-model="topicQuery" type="search" :placeholder="isMarketing ? '输入活动或产品名称关键词' : '输入选题标题关键词'" /></label>
              <label class="field"><span>选题类型</span><select :value="isMarketing ? 'marketing' : 'non_marketing'" disabled><option value="non_marketing">非营销</option><option value="marketing">营销</option></select></label>
              <label class="field"><span>选题二级分类</span><select v-model="contentType"><option value="">全部</option><option v-for="value in contentTypes" :key="value" :value="value">{{ value }}</option></select></label>
              <label class="field"><span>关联产品</span><select v-model="relatedProduct"><option value="">全部</option><option v-for="value in relatedProducts" :key="value" :value="value">{{ value }}</option></select></label>
              <label class="field"><span>关联活动</span><select v-model="relatedActivity"><option value="">全部</option><option v-for="value in relatedActivities" :key="value" :value="value">{{ value }}</option></select></label>
              <div class="query-filter-tail">
                <label class="field"><span>关联属地热点</span><select v-model="relatedHotspot"><option value="">全部</option><option v-for="value in relatedHotspots" :key="value" :value="value">{{ value }}</option></select></label>
                <div class="manual-topic-filter-actions query-filter-actions"><button class="text-btn manual-topic-clear-filters" type="button" @click="topicIdFilter = ''; topicQuery = ''; topicTypeFilter = isMarketing ? 'marketing' : 'non_marketing'; contentType = ''; relatedProduct = ''; relatedActivity = ''; relatedHotspot = ''">清空筛选</button><button class="btn primary filter-query-inline" type="button" @click="applyTopicFilters">查询</button></div>
              </div>
            </fieldset>
            <p class="manual-topic-validity-hint" role="note">{{ validityHint }}</p>
            <div class="manual-topic-list-meta"><b>符合条件 {{ filteredTopics.length }} 个</b></div>
            <LoadingSkeleton v-if="loading || !initialized" />
            <div v-else ref="topicListRef" class="table-wrap manual-topic-table"><MarketingTopicTable v-if="isMarketing" :topics="pagedTopics" selectable :selected-ids="selectedTopicIds" :readonly="topicReview" @select="setTopicSelected($event, true)" /><table v-else><thead><tr><th class="manual-topic-checkbox-cell">选择</th><th>选题 ID</th><th>选题标题</th><th>选题大纲</th><th>选题类型</th><th>选题二级分类</th><th>关联产品</th><th>关联活动</th><th>关联属地热点</th><th>有效期</th></tr></thead><tbody>
              <tr v-for="topic in pagedTopics" :key="topic.topic_id" :class="{ selected: selectedTopicIds.includes(topic.topic_id) }" class="selection-row" tabindex="0" :aria-disabled="topicReview || (!isMarketing && !selectedTopicIds.includes(topic.topic_id) && selectedTopicIds.length >= 100) || undefined" @click="toggleTopicRow(topic.topic_id, $event)" @keydown.enter.self.prevent="toggleTopicRow(topic.topic_id, $event)" @keydown.space.self.prevent="toggleTopicRow(topic.topic_id, $event)"><td class="manual-topic-checkbox-cell"><input :type="isMarketing ? 'radio' : 'checkbox'" :name="isMarketing ? 'marketing-topic' : undefined" :checked="selectedTopicIds.includes(topic.topic_id)" :disabled="topicReview || (!isMarketing && !selectedTopicIds.includes(topic.topic_id) && selectedTopicIds.length >= 100)" :aria-label="`选择选题 ${topic.topic_title}`" @change="setTopicSelected(topic.topic_id, $event.target.checked)" /></td><td>{{ topic.topic_id }}</td><td><HoverHint :text="topic.topic_title" :show-icon="false" class="manual-topic-title-tooltip"><span class="manual-topic-title-value">{{ topic.topic_title }}</span></HoverHint></td><td><div class="manual-topic-outline-value" :title="topic.outline || '暂无选题大纲'">{{ topic.outline || '\u6682\u65e0\u9009\u9898\u5927\u7eb2' }}</div></td><td><span class="topic-type-badge" :class="topic.is_marketing ? 'marketing' : 'non-marketing'">{{ topic.is_marketing ? '营销' : '非营销' }}</span></td><td>{{ topic.content_type || '\u2014' }}</td><td>{{ topic.related_product || '\u2014' }}</td><td>{{ topic.related_activity || '\u2014' }}</td><td>{{ topic.related_hotspot || '\u2014' }}</td><td><span class="manual-topic-validity">{{ topicValidityLabel(topic) }}</span></td></tr>
              <tr v-if="filteredTopics.length === 0"><td colspan="10"><div class="empty-state">没有符合条件的可用选题</div></td></tr>
            </tbody></table></div>
            <ListPagination :page.sync="topicPage" :page-size.sync="topicPageSize" :total="filteredTopics.length" unit="个选题" :page-size-options="[20, 50, 100]" class="manual-topic-pagination" />
          </section>
        </div>
          </div>
        </section>
        <section v-if="isMarketing" class="card manual-generation-settings" :class="{ waiting: !selectedTopics.length }" aria-label="生成内容数量">
          <div class="card-head manual-topic-substep-head"><h2><span class="manual-topic-substep-number" aria-hidden="true">2</span>设置生成内容数量</h2></div>
          <div class="card-body">
            <div v-if="selectedTopics[0]" class="manual-generation-selected"><span>已选选题</span><b :title="topicTooltip(selectedTopics[0])">{{ marketingTopicName(selectedTopics[0]) }}</b><small>{{ selectedTopics[0].topic_id }}</small></div>
            <label class="field manual-generation-count-field"><span class="field-label-with-tip">生成内容数量 <em>*</em><span class="field-help-tip" tabindex="0" title="根据所选选题需要生成的内容总条数，后续由外部系统分配账号。">?</span></span><div class="manual-generation-count-input"><input v-model.number="allocationCountModel" type="number" inputmode="numeric" min="1" max="1000" :placeholder="selectedTopics.length ? '请输入生成内容数量' : '请先选择选题'" :disabled="topicReview || !selectedTopics.length" required /><span>条</span></div></label>
          </div>
        </section>
        <div class="footer-actions manual-step-actions"><template v-if="topicReview"><div class="manual-step-review" role="status"><span class="manual-step-review-icon" aria-hidden="true">✓</span><strong>本次选择了 <em>{{ selectedTopicIds.length }}</em> 个选题进行策划，如需调整，请返回调整</strong><button class="btn" type="button" @click="topicReview = false">返回调整</button><button class="btn primary" type="button" @click="emit('next')">下一步</button></div></template><template v-else><button class="btn" type="button" @click="emit('back')">上一步</button><button class="btn primary" type="button" :disabled="!selectedTopicIds.length" @click="emit('save')">保存</button></template></div>
      </div>
    </section>

</template>
<style scoped>
.manual-topic-filters{min-width:0;margin:0;padding:0;border:0}
.manual-topic-validity-hint{margin:0 0 12px;color:var(--neutral-500);font-size:12px;line-height:20px}
.manual-topic-filters select:disabled{background:var(--neutral-100);color:var(--neutral-400);cursor:not-allowed}


.manual-account-filters,.manual-topic-filters{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));align-items:end;gap:12px;margin-bottom:18px}.manual-account-filters .field,.manual-topic-filters .field{min-width:0}.manual-account-filters input,.manual-account-filters select,.manual-topic-filters input,.manual-topic-filters select{box-sizing:border-box;width:100%;height:36px;padding:0 10px;border:1px solid var(--neutral-200);border-radius:7px;background:var(--surface);color:var(--neutral-900)}.manual-follower-range i,.manual-topic-validity i{color:var(--neutral-400);font-size:12px;font-style:normal;white-space:nowrap}.manual-account-list-meta,.manual-topic-list-meta{display:flex;justify-content:space-between;align-items:center;margin:0 0 8px;font-size:13px}.manual-account-list-meta span,.manual-topic-list-meta span{color:var(--neutral-400);font-size:12px}.manual-account-table,.manual-topic-table{max-height:430px;overflow:auto;border:1px solid var(--neutral-200);border-radius:8px}.manual-topic-table table{min-width:1160px}.manual-account-table thead th,.manual-topic-table thead th{position:sticky;top:0;z-index:1;background:var(--neutral-50);white-space:nowrap}.manual-account-table tbody tr:hover,.manual-account-table tbody tr.selected,.manual-topic-table tbody tr:hover,.manual-topic-table tbody tr.selected{background:var(--primary-50)}.manual-account-table input,.manual-topic-table input{accent-color:var(--primary-600)}.manual-account-pagination,.manual-topic-pagination{margin:14px 0 18px}.manual-topic-outline{display:block;max-width:360px;margin-top:4px;color:var(--neutral-400);font-size:11px;line-height:1.5;white-space:normal}.manual-topic-validity{display:flex;align-items:center;gap:5px;white-space:nowrap;font-size:12px}.manual-step-review{display:flex;align-items:center;gap:10px;flex:1;min-width:0;padding:10px 12px;border:1px solid var(--primary-100);border-radius:8px;background:var(--primary-50)}.manual-step-review-icon{display:grid;place-items:center;flex:none;width:24px;height:24px;border-radius:50%;background:var(--primary-50);color:var(--primary-600);font-size:14px;font-weight:700}.manual-step-review>strong{flex:1;min-width:0;color:var(--neutral-700);font-size:13px;font-weight:500;line-height:1.5}.manual-step-review>strong em{display:inline-block;margin:0 2px;color:var(--primary-600);font-size:20px;font-style:normal;font-weight:700;font-variant-numeric:tabular-nums;line-height:1;vertical-align:-1px}
@media(max-width:900px){.manual-account-filters,.manual-topic-filters{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:580px){.manual-account-filters,.manual-topic-filters,.manual-submit-summary{grid-template-columns:1fr}.manual-topic-list-meta{align-items:flex-start;gap:6px;flex-direction:column}.manual-step-review{flex-wrap:wrap}.manual-step-review>strong{flex-basis:calc(100% - 36px)}.manual-step-review .btn{flex:1}}.manual-topic-filters .field{width:100%}
.manual-marketing-topic-group{grid-column:1/-1}
.manual-topic-picker.single-topic-picker{grid-template-columns:minmax(0,1fr)}
.manual-topic-substep-head h2{display:flex;align-items:center;gap:10px}
.manual-topic-substep-number{display:inline-grid;place-items:center;flex:none;width:24px;height:24px;border-radius:50%;background:var(--primary-50);color:var(--primary-600);font-size:12px;font-weight:600}
.manual-generation-settings.waiting .manual-topic-substep-number{background:var(--neutral-100);color:var(--neutral-400)}
.manual-marketing-topic-step .manual-topic-selection-section{margin-bottom:20px}
.manual-marketing-topic-step .manual-generation-settings{margin-bottom:0}
.manual-marketing-topic-step .manual-topic-pagination{margin-bottom:0}
.manual-marketing-topic-step .manual-topic-table{max-height:300px}
.manual-generation-selected{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:14px;color:var(--neutral-500);font-size:12px}
.manual-generation-selected b{min-width:0;max-width:520px;overflow:hidden;color:var(--neutral-800);font-size:13px;text-overflow:ellipsis;white-space:nowrap}
.manual-generation-selected small{color:var(--neutral-400);font-size:12px;overflow-wrap:anywhere}
.manual-generation-count-field{display:flex;flex-direction:row;align-items:center;flex-wrap:wrap;gap:16px;margin:0}
.manual-generation-count-field>span{color:var(--neutral-600);font-size:13px;white-space:nowrap}
.manual-generation-count-input{display:flex;align-items:center;gap:8px;color:var(--neutral-500);font-size:13px}
.manual-generation-count-input input{box-sizing:border-box;width:190px;height:36px;padding:0 12px;border:1px solid var(--neutral-200);border-radius:6px;background:var(--surface);color:var(--neutral-900)}
@media(max-width:580px){.manual-generation-count-field{gap:8px}.manual-generation-count-input input{width:156px}}
.manual-topic-table :deep(.manual-topic-title-tooltip){display:flex;width:100%;min-width:0;color:var(--neutral-800);font-size:13px;font-weight:500;text-align:left;line-height:1.6}
.manual-topic-table :deep(.manual-topic-title-tooltip:hover),.manual-topic-table :deep(.manual-topic-title-tooltip:focus-visible){color:var(--neutral-800);text-decoration:none}
.manual-topic-table table{min-width:1328px}.manual-topic-table .manual-topic-checkbox-cell{width:48px;min-width:48px;padding:0 12px;text-align:center}.manual-topic-checkbox-cell input{vertical-align:middle}.manual-topic-table td:nth-child(3){width:220px;max-width:220px}.manual-topic-table td:nth-child(4){width:300px;max-width:300px}.manual-topic-title-value,.manual-topic-outline-value{display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.manual-topic-outline-value{color:var(--neutral-600);font-size:12px}.manual-topic-filter-actions{grid-column:1/-1;display:flex;justify-content:flex-end;gap:8px}
.manual-topic-picker{display:grid;grid-template-columns:minmax(250px,300px) minmax(0,1fr);gap:16px;align-items:start}.manual-topic-picker-available{min-width:0}.manual-topic-picker-available .manual-topic-pagination{margin-bottom:0}.manual-topic-picked{position:sticky;top:16px;min-width:0;overflow:hidden;border:1px solid var(--neutral-200);border-radius:9px;background:var(--surface)}.manual-topic-picked-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:13px 14px;border-bottom:1px solid var(--neutral-100);color:var(--neutral-700);font-size:13px}.manual-topic-picked-head span{color:var(--primary-600);font-size:12px;font-variant-numeric:tabular-nums;font-weight:600}.manual-topic-picked-list{max-height:480px;overflow:auto;padding:0 14px}.manual-topic-picked-item{display:flex;align-items:flex-start;gap:8px;padding:11px 0;border-bottom:1px solid var(--neutral-100)}.manual-topic-picked-item:last-child{border-bottom:0}.manual-topic-picked-item>div{flex:1;min-width:0}.manual-topic-picked-item b{display:block;color:var(--neutral-800);font-size:13px;line-height:1.45;overflow-wrap:anywhere}.manual-topic-picked-item small{display:block;margin-top:4px;color:var(--neutral-400);font-size:11px}.manual-topic-picked-item .remove-topic{flex:none;margin-top:-3px}.manual-topic-picked-empty{display:grid;min-height:110px;place-items:center;color:var(--neutral-400);font-size:12px}
.manual-step-body{padding-bottom:104px}.manual-step-actions{position:fixed;z-index:35;right:0;bottom:0;left:var(--sidebar-width);display:flex;align-items:center;justify-content:flex-end;min-height:68px;margin:0;padding:12px 32px calc(12px + env(safe-area-inset-bottom));border-top:1px solid var(--neutral-200);background:color-mix(in srgb,var(--surface) 94%,transparent);box-shadow:0 -6px 20px #1018280a;backdrop-filter:blur(10px)}
@media(max-width:900px){.manual-topic-picker{grid-template-columns:240px minmax(0,1fr);gap:12px}}
@media(max-width:780px){.manual-step-actions{padding-right:24px;padding-left:24px}}
@media(max-width:700px){.manual-topic-picker{grid-template-columns:1fr}.manual-topic-picked{position:static;grid-row:1}.manual-topic-picked-list{max-height:240px}}
@media(max-width:580px){.manual-step-body{padding-bottom:124px}.manual-step-actions{min-height:76px;padding:10px 12px calc(10px + env(safe-area-inset-bottom))}.manual-step-actions .manual-step-review{width:100%;flex-wrap:wrap}.manual-step-actions .manual-step-review>strong{flex-basis:calc(100% - 36px)}.manual-step-actions .manual-step-review .btn{flex:1}}

</style>
