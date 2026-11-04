<script lang="ts">
import { defineComponent, type PropType } from '../../compat/composition';
import { computed, watch } from '../../compat/composition';
import type { LifecycleRule } from '../../types';
import { lifecycleRuleSummary, lifecycleGroups, lifecycleMetricOptions, lifecycleOperatorOptions, metricUnit, addLifecycleCondition, addLifecycleGroup, removeLifecycleCondition, normalizeLifecycleRule } from '../../ui/lifecycleRules';
export default defineComponent({
    props: { value: { required: true, type: Array as PropType<LifecycleRule[]> } },
    setup(props, context) {
        const emit = context.emit;
        const lifecycleRules = computed({
            get: () => props.value,
            set: value => emit('input', value)
        });
        watch(lifecycleRules, rules => {
            for (const rule of rules)
                if (!rule.catchAll)
                    normalizeLifecycleRule(rule);
        }, {
            immediate: true
        });
        return {
            lifecycleRuleSummary,
            lifecycleGroups,
            lifecycleMetricOptions,
            lifecycleOperatorOptions,
            metricUnit,
            addLifecycleCondition,
            addLifecycleGroup,
            removeLifecycleCondition,
            lifecycleRules
        };
    }
});
</script>
<template>
<div class="lifecycle-editor">
        <div class="lifecycle-definition-head"><div><b>生命周期阶段判定</b></div></div>
        <div class="lifecycle-definition-list">
          <div v-for="rule in lifecycleRules" :key="rule.name" class="lifecycle-definition lifecycle-grouped-rule">
            <div class="lifecycle-rule-heading"><b>{{ rule.name }}</b><span class="lifecycle-rule-summary">{{ lifecycleRuleSummary(rule,lifecycleRules) }}</span></div>
            <template v-if="!rule.catchAll">
              <template v-for="(group, groupIndex) in lifecycleGroups(rule)" >
                <div :key="(groupIndex) + '-0'" v-if="groupIndex" class="lifecycle-or">或</div>
                <div :key="(groupIndex) + '-1'" class="lifecycle-condition-group">
                  <div v-for="(condition, conditionIndex) in group" :key="conditionIndex" class="lifecycle-group-row">
                    <span v-if="conditionIndex" class="lifecycle-and">且</span><span v-else class="lifecycle-and-placeholder"></span>
                    <select v-model="condition.field" aria-label="指标"><option v-for="option in lifecycleMetricOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select>
                    <select v-model="condition.operator" aria-label="运算符"><option v-for="option in lifecycleOperatorOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select>
                    <input v-model.number="condition.value" type="number" min="0" step="1" aria-label="阈值" /><span>{{ metricUnit(condition.field) }}</span>
                    <button v-if="rule.conditions.length > 1" class="icon-btn" type="button" aria-label="删除条件" @click="removeLifecycleCondition(rule, groupIndex, conditionIndex)">×</button>
                  </div>
                  <button class="text-btn" type="button" @click="addLifecycleCondition(rule, groupIndex)">＋ 添加且条件</button>
                </div>
              </template>
              <button class="text-btn lifecycle-add-group" type="button" @click="addLifecycleGroup(rule)">＋ 添加或条件组</button>
            </template>
          </div>
        </div>

</div>
</template>
<style scoped>

.config-overview-body .lifecycle-summary-table th:first-child { width: 160px; }
.config-overview-body .lifecycle-summary-table th:nth-child(2), .config-overview-body .lifecycle-summary-table td:nth-child(2) { width: auto; text-align: left; white-space: normal; overflow-wrap: anywhere; }
.lifecycle-grouped-rule{display:block;padding:12px 14px}
.lifecycle-rule-heading{display:flex;align-items:center;gap:14px;min-height:32px}.lifecycle-rule-heading>b{flex:0 0 90px}.lifecycle-rule-heading>.text-btn{display:none}.lifecycle-rule-summary{flex:1;padding:7px 10px;border-radius:6px;background:var(--neutral-50);color:var(--neutral-600);font-size:12px;line-height:20px}
.lifecycle-condition-group{margin:10px 0;padding:12px;border:1px solid var(--neutral-200);border-radius:7px}.lifecycle-group-row{display:flex;align-items:center;gap:8px;margin-bottom:8px;color:var(--neutral-500);font-size:12px}.lifecycle-group-row select,.lifecycle-group-row input{height:32px;padding:0 8px;border:1px solid var(--neutral-200);border-radius:6px;background:var(--surface)}.lifecycle-group-row select:first-of-type{width:155px}.lifecycle-group-row select:nth-of-type(2){width:64px}.lifecycle-group-row input{width:86px}.lifecycle-and,.lifecycle-or{color:var(--primary-600);background:var(--primary-50);border-radius:12px;padding:3px 8px;font-size:12px}.lifecycle-and-placeholder{width:28px}.lifecycle-or{display:inline-block}.lifecycle-add-group{margin-top:4px}@media(max-width:600px){.lifecycle-rule-heading{flex-wrap:wrap}.lifecycle-rule-summary{flex-basis:100%;order:3}.lifecycle-group-row{flex-wrap:wrap}}
.lifecycle-definition-head{margin:14px 0 10px;padding-top:12px;font-size:13px}
.lifecycle-definition-list{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;align-items:start}
.lifecycle-definition{min-width:0;grid-template-columns:minmax(0,1fr);gap:8px;padding:11px 12px;background:var(--neutral-50);border-color:var(--neutral-200)}
.lifecycle-stage-name{padding:0}
.lifecycle-stage-name b{font-size:14px;line-height:22px;font-weight:600}
.lifecycle-condition-list{gap:6px}
.lifecycle-condition-row{display:grid;grid-template-columns:minmax(110px,1fr) 48px 68px 40px 44px 22px;gap:6px;max-width:560px}
.lifecycle-condition-row select,.lifecycle-condition-row input{width:100%;min-width:0;height:32px;padding:0 6px;border-radius:6px;font-size:13px}
.lifecycle-condition-row input{text-align:center}
.lifecycle-definition.is-catch-all{grid-column:1/-1;grid-template-columns:100px minmax(0,1fr);align-items:center;background:var(--neutral-50)}
.lifecycle-catch-all{font-size:12px;line-height:1.6;color:var(--neutral-500)}
@media(max-width:1100px){.lifecycle-definition-list{grid-template-columns:minmax(0,1fr)}}
@media(max-width:780px){.lifecycle-definition.is-catch-all{grid-template-columns:minmax(0,1fr);gap:5px}}
@media(max-width:580px){.lifecycle-condition-row{grid-template-columns:48px 64px minmax(0,1fr) 44px 22px}.lifecycle-condition-row select:first-child{grid-column:1/-1;grid-row:1;min-width:0}.lifecycle-condition-row select:nth-child(2){grid-column:1;grid-row:2}.lifecycle-condition-row input{grid-column:2;grid-row:2}.lifecycle-definition{padding:10px}}

</style>
