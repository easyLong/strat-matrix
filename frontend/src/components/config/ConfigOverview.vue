<script lang="ts">
import { defineComponent, type PropType } from '../../compat/composition';
import { computed } from '../../compat/composition';
import TaxonomyPanel from '../TaxonomyPanel.vue';
import ProductionTimingConfig from './ProductionTimingConfig.vue';
import type { StrategyConfig } from '../../types';
import type { TagTaxonomyItem } from '../../api';
import { lifecycleRuleSummary } from '../../ui/lifecycleRules';
export default defineComponent({
    props: { config: { required: true, type: null as unknown as PropType<StrategyConfig> },
        tagItems: { required: true, type: Object as PropType<Record<string, TagTaxonomyItem[]>> } },
    setup(props, context) {
        const planningDays = computed(() => props.config.planning_days);
        const scheduleDay = computed(() => props.config.schedule_day);
        const scheduleTime = computed(() => props.config.schedule_time);
        const lifecycleRules = computed(() => props.config.lifecycle_rules);
        return {
            lifecycleRuleSummary,
            planningDays,
            scheduleDay,
            scheduleTime,
            lifecycleRules
        };
    },
    components: {TaxonomyPanel, ProductionTimingConfig}
});
</script>
<template>
<div class="vue2-component-root">
  <section class="card config-overview-card">
    <div class="card-head"><div><h2>策划内容配置</h2></div></div>
    <div class="card-body config-overview-body">
      <div class="config-at-glance">
        <div class="config-glance-item config-glance-days"><span>每周策划日</span><div class="config-glance-days-list"><b v-for="day in planningDays" :key="day">{{ ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][day - 1] }}</b></div></div>
        <div class="config-glance-item"><span>自动策划调度时间</span><b>每周{{ ['一', '二', '三', '四', '五', '六', '日'][scheduleDay - 1] }} {{ scheduleTime }}</b></div>
        <div class="config-glance-item"><span>营销内容周上限</span><b>{{ config.marketing_max }} 条 / 营销账号</b></div>
        <div class="config-glance-item"><span>热点选题占比</span><b>{{ config.hotspot_ratio }}%</b></div>
      </div>
      <ProductionTimingConfig :value="config.content_production_lead_days" readonly />
    </div>
  </section>
  <section class="card config-overview-card">
    <div class="card-head"><div><h2>策划规则配置</h2></div></div>
    <div class="card-body config-overview-body">
      <section class="config-readonly-panel">
        <div class="config-readonly-panel-head"><h3>生命周期阶段判定</h3></div>
        <div class="stage-table-wrap">
          <table class="stage-table config-readonly-stage-table lifecycle-summary-table"><thead><tr><th>阶段</th><th>进入条件</th></tr></thead>
            <tbody><tr v-for="rule in lifecycleRules" :key="rule.name">
              <td><b>{{ rule.name }}</b></td><td>{{ lifecycleRuleSummary(rule, lifecycleRules) }}</td>
            </tr></tbody>
          </table>
        </div>
      </section>
      <section class="config-readonly-panel">
        <div class="config-readonly-panel-head"><h3>阶段经营目标</h3></div>
        <div class="stage-table-wrap">
          <table class="stage-table config-readonly-stage-table"><thead><tr><th>生命周期阶段</th><th>流量目标</th><th>转化目标</th></tr></thead>
            <tbody><tr v-for="stage in config.stage_targets" :key="stage.name">
              <td><b>{{ stage.name }}</b></td><td>{{ stage.traffic }}%</td><td>{{ stage.conversion }}%</td>
            </tr></tbody>
          </table>
        </div>
      </section>
      <section class="config-readonly-panel">
        <div class="config-readonly-panel-head"><h3>滚动统计窗口</h3><span><b>{{ config.rolling_posts }} 篇</b></span></div>
      </section>
      <section class="config-readonly-panel config-readonly-tag-panel">
        <div class="config-readonly-panel-head"><h3>选题标签配置</h3></div>
        <TaxonomyPanel :model-value="tagItems" />
      </section>
    </div>
  </section>

</div>
</template>
<style scoped>

.config-overview-body .lifecycle-summary-table th:first-child { width: 160px; }
.config-overview-body .lifecycle-summary-table th:nth-child(2), .config-overview-body .lifecycle-summary-table td:nth-child(2) { width: auto; text-align: left; white-space: normal; overflow-wrap: anywhere; }
@media(max-width:580px){.config-readonly-stage-table{min-width:540px}}
.config-readonly-panel-head h3{font-size:14px;line-height:22px;font-weight:600}
.config-readonly-stage-table th,.config-readonly-stage-table td{padding:8px;font-size:13px;line-height:20px}
.config-readonly-stage-table th:nth-child(1){width:22%}
.config-readonly-stage-table th:nth-child(2),.config-readonly-stage-table th:nth-child(3){width:10%}
.config-readonly-stage-table th:nth-child(4){width:58%}
.config-readonly-tag-title{font-size:12px;line-height:18px}
.config-readonly-tag-row .tag-pills{gap:6px}
.config-readonly-tag-row .tag{padding:2px 7px;border:1px solid var(--label-border);border-radius:4px;background:var(--label-background);color:var(--label-color);font-size:11px;line-height:16px}
.config-readonly-tag-row .tag.disabled{border-style:dashed;border-color:var(--neutral-200);background:var(--neutral-50);color:var(--neutral-400)}
.config-readonly-columns{grid-template-columns:minmax(0,1fr)}.config-readonly-tag-panel{padding:0;overflow:hidden}.config-readonly-tag-panel .config-readonly-panel-head{padding:15px 18px;margin:0}

</style>
