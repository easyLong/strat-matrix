<script lang="ts">
import { computed, defineComponent, type PropType } from '../../compat/composition'
import type { LifecycleCondition, LifecycleRule } from '../../types'
import { coldStartSummary, lifecycleGroups, lifecycleMetricOptions, normalizeLifecycleRule } from '../../ui/lifecycleRules'
import { lifecycleRangeRows } from '../../ui/lifecycleRanges'

export default defineComponent({
  props: { rule: { type: Object as PropType<LifecycleRule>, required: true },
    rules: { type: Array as PropType<LifecycleRule[]>, required: true }, compact: Boolean },
  setup(props) {
    const groups = computed(() => {
      if (props.rule.catchAll) return []
      // Presentation normalizes a copy; reading a rule must never mutate saved configuration.
      const rule = { ...props.rule, conditions: props.rule.conditions.map(item => ({ ...item })) }
      normalizeLifecycleRule(rule)
      const value = (condition: LifecycleCondition) => Number.isFinite(condition.value) ? String(condition.value) : '待填写'
      return lifecycleGroups(rule).map(group => lifecycleRangeRows(group).map(row => {
        const metric = lifecycleMetricOptions.find(metric => metric.value === row.field)
        let range = ''
        if (row.exact !== undefined) range = `= ${value(group[row.exact])}`
        else if (row.lower !== undefined && row.upper !== undefined) {
          const lower = group[row.lower], upper = group[row.upper]
          range = `${value(lower)}（${lower.operator === 'gt' ? '不含' : '含'}）～${value(upper)}（${upper.operator === 'lt' ? '不含' : '含'}）`
        } else {
          const bound = group[row.lower ?? row.upper ?? 0]
          const operator = { gt: '>', gte: '≥', lt: '<', lte: '≤', eq: '=' }[bound.operator]
          range = `${operator} ${value(bound)}`
        }
        return { label: metric?.label || row.field, range: `${range} ${metric?.unit || ''}`.trim() }
      }))
    })
    return { groups, fallback: computed(() => coldStartSummary(props.rules)) }
  },
})
</script>
<template>
  <div class="lifecycle-rule-summary" :class="{ compact }" :aria-label="`${rule.name}条件摘要`">
    <span v-if="rule.catchAll" class="lifecycle-fallback-summary">{{ fallback }}</span>
    <template v-for="(group,index) in groups">
      <span v-if="index" :key="`or-${index}`" class="summary-or">或</span>
      <div :key="`group-${index}`" class="summary-condition-group">
        <template v-for="(condition,conditionIndex) in group">
          <span v-if="conditionIndex" :key="`and-${conditionIndex}`" class="summary-and">且</span>
          <span :key="`condition-${conditionIndex}`" class="summary-condition"><span>{{ condition.label }}</span><strong>{{ condition.range }}</strong></span>
        </template>
      </div>
    </template>
  </div>
</template>
<style scoped>
.lifecycle-rule-summary{display:flex;flex-wrap:wrap;align-items:center;gap:8px;min-width:0;font-size:13px;line-height:22px;color:var(--text-secondary)}
.summary-condition-group{display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px;max-width:100%;min-width:0;padding:8px 12px;border-radius:12px;background:var(--primary-50)}
.summary-condition{display:inline-flex;flex-wrap:wrap;align-items:baseline;gap:5px;min-width:0;overflow-wrap:anywhere}
.summary-condition strong{color:var(--primary-700);font-weight:500;font-variant-numeric:tabular-nums}
.summary-or{flex:none;display:grid;place-items:center;min-width:24px;min-height:24px;padding:0 4px;border-radius:12px;background:var(--primary-50);color:var(--primary-600);font-weight:500}
.summary-and{color:var(--text-muted);font-size:12px}
.lifecycle-fallback-summary{overflow-wrap:anywhere}
.compact .summary-condition-group{padding:4px 8px;border-radius:6px}
.compact .summary-condition,.compact .summary-or{font-size:12px;line-height:20px}
</style>
