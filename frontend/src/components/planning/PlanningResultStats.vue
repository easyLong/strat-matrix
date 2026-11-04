<script lang="ts">
import { defineComponent, type PropType } from '../../compat/composition';
import { computed } from '../../compat/composition';
import HoverHint from '../HoverHint.vue';
import type { ContentTypeCount } from '../../ui/contentTypeStats';
export default defineComponent({
    props: { mode: { required: true, type: String as PropType<'account' | 'cycle' | 'batch'> },
        summary: { required: true, type: Object as PropType<{
                accounts: number;
                batches: number;
                topics: number;
            }> },
        distribution: { required: true, type: Array as PropType<ContentTypeCount[]> } },
    setup(props, context) {
        const isAccountMode = computed(() => props.mode === 'account');
        const isBatchMode = computed(() => props.mode === 'batch');
        const dashboard = computed(() => props.summary);
        const topicTypeCounts = computed(() => [...props.distribution].sort((a, b) => b.count - a.count));
        return {
            isAccountMode,
            isBatchMode,
            dashboard,
            topicTypeCounts
        };
    },
    components: {HoverHint}
});
</script>
<template>
<div class="vue2-component-root">
      <section class="planning-dashboard" aria-label="策划概览">
        <div v-if="isAccountMode">
          <HoverHint class="dashboard-label" text="当前账号历史策划记录中去重后的批次数量" :show-icon="true">覆盖批次</HoverHint>
          <strong>{{ dashboard.batches }}</strong>
        </div>
        <div v-else>
          <HoverHint class="dashboard-label" text="当前批次或周期内去重后的账号数量" :show-icon="true">参与账号</HoverHint>
          <strong>{{ dashboard.accounts }}</strong>
        </div>
        <div>
          <HoverHint class="dashboard-label" text="当前查看范围内去重后的选题 ID 数量" :show-icon="true">使用选题</HoverHint>
          <strong>{{ dashboard.topics }}</strong>
        </div>
      </section>

 <slot />
      <section class="batch-topic-types" :aria-labelledby="isBatchMode ? 'batch-topic-types-title' : 'detail-topic-types-title'">
        <h3 :id="isBatchMode ? 'batch-topic-types-title' : 'detail-topic-types-title'"><HoverHint text="按去重后的选题 ID 统计各二级分类分布" :show-icon="true">选题二级分类分布</HoverHint></h3>
        <dl>
          <div v-for="type in topicTypeCounts" :key="type.name" :title="type.hint">
            <dt>{{ type.name }}</dt><dd :class="{ empty: type.count === 0 }">{{ type.count }}</dd>
          </div>
        </dl>
      </section>

</div>
</template>
<style scoped>

.batch-topic-types{margin:0 20px 16px;padding:0 0 4px}.batch-topic-types h3{margin:0 0 8px;color:var(--neutral-700);font-size:13px;line-height:22px;font-weight:600}.batch-topic-types h3 .hover-hint{font-size:13px;font-weight:600;color:var(--neutral-700)}.batch-topic-types dl{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));column-gap:20px;margin:0}.batch-topic-types dl>div{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0;padding:9px 0;border-bottom:1px solid var(--neutral-100)}.batch-topic-types dt{color:var(--neutral-500);font-size:12px;line-height:20px;overflow-wrap:anywhere}.batch-topic-types dd{flex:none;margin:0;color:var(--neutral-800);font-size:14px;line-height:20px;font-weight:500;font-variant-numeric:tabular-nums}.batch-topic-types dd.empty{color:var(--neutral-400);font-weight:400}
@media(max-width:1200px){.batch-topic-types dl{grid-template-columns:repeat(4,minmax(0,1fr))}}@media(max-width:980px){.batch-topic-types{margin:0 12px 16px}.batch-topic-types dl{grid-template-columns:repeat(3,minmax(0,1fr));column-gap:16px}}@media(max-width:580px){.batch-topic-types dl{grid-template-columns:repeat(2,minmax(0,1fr));column-gap:12px}}
.planning-dashboard{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;margin:16px 20px 16px;border:1px solid var(--neutral-200);border-radius:12px;overflow:hidden;background:var(--neutral-200)}
.planning-dashboard>div{display:flex;flex-direction:column;gap:8px;min-height:74px;padding:14px 16px;background:var(--surface)}
.planning-dashboard .dashboard-label{justify-content:flex-start;color:var(--neutral-500);font-size:12px}.planning-dashboard strong{color:var(--neutral-800);font-size:22px;line-height:1;font-variant-numeric:tabular-nums}
@media(max-width:980px){.planning-dashboard{grid-template-columns:repeat(3,minmax(0,1fr));margin:12px}}
@media(max-width:580px){.planning-dashboard{grid-template-columns:repeat(2,minmax(0,1fr))}}

</style>
