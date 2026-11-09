<script>
import TaxonomyPanel from '../TaxonomyPanel.vue';
import ProductionTimingConfig from './ProductionTimingConfig.vue';
import LifecycleRuleSummary from './LifecycleRuleSummary.vue';
export default {
  props: {
    config: {
      required: true,
      type: null
    },
    tagItems: {
      required: true,
      type: Object
    }
  },
  components: {
    TaxonomyPanel,
    ProductionTimingConfig,
    LifecycleRuleSummary
  },
  data() {
    return {
      rulesExpanded: true
    };
  },
  computed: {
    planningDays() {
      return this.config.planning_days;
    },
    scheduleDay() {
      return this.config.schedule_day;
    },
    scheduleTime() {
      return this.config.schedule_time;
    },
    lifecycleRules() {
      return this.config.lifecycle_rules;
    },
    targets() {
      return Object.fromEntries(this.config.stage_targets.map(stage => [stage.name, stage]));
    }
  }
};
</script>
<template>
<div class="vue2-component-root">
  <section class="card config-overview-card">
    <div class="card-head"><h2>策划内容配置</h2><div class="config-overview-actions"><slot name="actions" /></div></div>
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
    <div class="card-head config-rules-head"><h2>策划规则配置</h2><div class="config-window-inline"><span>滚动统计窗口</span><b>{{ config.rolling_posts }} 篇</b></div><button class="text-btn config-section-toggle" type="button" :aria-expanded="rulesExpanded" @click="rulesExpanded=!rulesExpanded">{{ rulesExpanded ? '收起' : '展开' }} <span aria-hidden="true">{{ rulesExpanded ? '⌃' : '⌄' }}</span></button></div>
    <div v-show="rulesExpanded" class="card-body config-overview-body">
      <section class="config-readonly-panel">
        <div class="config-readonly-panel-head"><h3>生命周期阶段判定</h3></div>
        <div class="stage-table-wrap">
          <table class="stage-table config-readonly-stage-table lifecycle-summary-table"><thead><tr><th>阶段</th><th>进入条件</th><th>流量目标</th><th>转化目标</th></tr></thead>
            <tbody><tr v-for="rule in lifecycleRules" :key="rule.name">
              <td><b>{{ rule.name }}</b></td><td><LifecycleRuleSummary :rule="rule" :rules="lifecycleRules" compact /></td><td>{{ targets[rule.name] ? `${targets[rule.name].traffic}%` : '—' }}</td><td>{{ targets[rule.name] ? `${targets[rule.name].conversion}%` : '—' }}</td>
            </tr></tbody>
          </table>
        </div>
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
.config-overview-actions{display:flex;flex-wrap:wrap;gap:8px;margin-left:auto}
.config-overview-body .config-readonly-panel{min-width:0;padding:0;border:0;border-radius:0}
.config-overview-body .config-readonly-panel+.config-readonly-panel{margin-top:20px;padding-top:20px;border-top:1px solid var(--divider)}
.config-overview-body .config-readonly-panel-head{padding:0;margin:0 0 12px}
.config-readonly-panel-head h3{font-size:14px;line-height:22px;font-weight:600}
.config-overview-body .lifecycle-summary-table{width:100%;table-layout:fixed}
.config-overview-body .lifecycle-summary-table th:first-child{width:140px}
.config-overview-body .lifecycle-summary-table th:nth-child(2),.config-overview-body .lifecycle-summary-table td:nth-child(2){width:auto;text-align:left;white-space:normal;overflow-wrap:anywhere}
.config-overview-body .lifecycle-summary-table th:nth-child(3),.config-overview-body .lifecycle-summary-table th:nth-child(4){width:90px;text-align:center}
.config-overview-body .lifecycle-summary-table td:nth-child(3),.config-overview-body .lifecycle-summary-table td:nth-child(4){text-align:center;white-space:nowrap}
.config-overview-body .lifecycle-summary-table th,.config-overview-body .lifecycle-summary-table td{padding:10px 8px;font-size:13px;line-height:20px;vertical-align:middle}
@media(max-width:580px){.config-overview-body .lifecycle-summary-table{min-width:540px}}
</style>
