<script lang="ts">
import { computed, defineComponent, ref, watch, type PropType } from '../../compat/composition'
import type { LifecycleCondition, LifecycleRule } from '../../types'
import LifecycleRuleSummary from './LifecycleRuleSummary.vue'
import { lifecycleGroups, lifecycleMetricOptions, metricUnit, addLifecycleCondition, addLifecycleGroup, normalizeLifecycleRule } from '../../ui/lifecycleRules'
import { lifecycleRangeRows, lifecycleRangeValid, updateLifecycleBound, updateLifecycleRangeField, removeLifecycleRange } from '../../ui/lifecycleRanges'

export default defineComponent({
  props: { value: { type: Array as PropType<LifecycleRule[]>, required: true } },
  setup(props) {
    const active = ref(props.value[0]?.name || '')
    const expanded = ref(true)
    watch(() => props.value, rules => {
      rules.filter(rule => !rule.catchAll).forEach(normalizeLifecycleRule)
      if (!rules.some(rule => rule.name === active.value)) active.value = rules[0]?.name || ''
    }, { immediate: true })
    const current = computed(() => props.value.find(rule => rule.name === active.value))
    function moveTab(event: KeyboardEvent) {
      const index = props.value.findIndex(rule => rule.name === active.value)
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? props.value.length - 1 : event.key === 'ArrowRight' ? (index + 1) % props.value.length : event.key === 'ArrowLeft' ? (index + props.value.length - 1) % props.value.length : -1
      if (next < 0) return
      event.preventDefault()
      active.value = props.value[next]!.name
      ;(event.currentTarget as HTMLElement).parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus()
    }
    const boundValue = (condition?: LifecycleCondition) => condition && Number.isFinite(condition.value) ? condition.value : ''
    return { active, expanded, current, moveTab, boundValue, lifecycleGroups, lifecycleMetricOptions, metricUnit, lifecycleRangeRows, lifecycleRangeValid, updateLifecycleBound, updateLifecycleRangeField, removeLifecycleRange, addLifecycleCondition, addLifecycleGroup }
  },
  components: { LifecycleRuleSummary },
})
</script>
<template>
  <div class="lifecycle-editor">
    <div class="lifecycle-global-head"><h3>生命周期阶段判定</h3><button class="text-btn" type="button" :aria-expanded="expanded" @click="expanded=!expanded">{{ expanded ? '收起' : '展开' }} <span aria-hidden="true">{{ expanded ? '⌃' : '⌄' }}</span></button></div>
    <div v-show="expanded">
      <div class="lifecycle-stage-tabs" role="tablist" aria-label="生命周期阶段">
        <button v-for="(rule, index) in value" :id="`lifecycle-tab-${index}`" :key="rule.name" type="button" role="tab" :class="{ active:active===rule.name }" :aria-selected="active===rule.name" aria-controls="lifecycle-stage-panel" :tabindex="active===rule.name ? 0 : -1" @click="active=rule.name" @keydown="moveTab">{{ rule.name }}</button>
      </div>
      <section v-if="current" id="lifecycle-stage-panel" role="tabpanel" :aria-labelledby="`lifecycle-tab-${value.indexOf(current)}`" class="lifecycle-stage-panel">
        <LifecycleRuleSummary class="lifecycle-summary-preview" :rule="current" :rules="value" />
        <template v-if="!current.catchAll">
          <template v-for="(group, groupIndex) in lifecycleGroups(current)">
            <div v-if="groupIndex" :key="`or-${groupIndex}`" class="lifecycle-or">或满足下一组</div>
            <div :key="`group-${groupIndex}`" class="lifecycle-condition-group">
              <div class="lifecycle-group-caption"><span>条件组 {{ groupIndex+1 }} · 全部满足</span><button class="text-btn" type="button" @click="addLifecycleCondition(current,groupIndex)">＋ 添加条件</button></div>
              <div v-for="(row,rowIndex) in lifecycleRangeRows(group)" :key="rowIndex" class="lifecycle-range-row">
                <label class="field lifecycle-metric"><span>指标</span><select :value="row.field" aria-label="指标" @change="updateLifecycleRangeField(current,groupIndex,row,$event.target.value)"><option v-for="metric in lifecycleMetricOptions" :key="metric.value" :value="metric.value">{{ metric.label }}</option></select></label>
                <template v-if="row.exact===undefined">
                  <label class="field"><span>起始值{{ row.lower!==undefined && group[row.lower].operator==='gt' ? '（不含）' : '（含）' }}</span><input :value="row.lower===undefined ? '' : boundValue(group[row.lower])" type="number" min="0" step="1" placeholder="不限" :aria-label="`${metricUnit(row.field)}起始值`" @input="updateLifecycleBound(current,groupIndex,row,'lower',$event.target.value)" /></label>
                  <span class="lifecycle-range-separator" aria-hidden="true">～</span>
                  <label class="field"><span>截止值{{ row.upper!==undefined && group[row.upper].operator==='lt' ? '（不含）' : '（含）' }}</span><input :value="row.upper===undefined ? '' : boundValue(group[row.upper])" type="number" min="0" step="1" placeholder="不限" :aria-label="`${metricUnit(row.field)}截止值`" @input="updateLifecycleBound(current,groupIndex,row,'upper',$event.target.value)" /></label>
                </template>
                <label v-else class="field"><span>等于</span><input :value="boundValue(group[row.exact])" type="number" min="0" step="1" aria-label="精确值" @input="updateLifecycleBound(current,groupIndex,row,'exact',$event.target.value)" /></label>
                <span class="lifecycle-range-unit">{{ metricUnit(row.field) }}</span>
                <button class="icon-btn" type="button" aria-label="删除条件" :disabled="current.conditions.length===[row.lower,row.upper,row.exact].filter(i=>i!==undefined).length" @click="removeLifecycleRange(current,groupIndex,row)">×</button>
                <span v-if="!lifecycleRangeValid(group,row)" class="lifecycle-range-error" role="alert">请填写有效范围，起始值不能大于截止值</span>
              </div>
            </div>
          </template>
          <button class="text-btn lifecycle-add-group" type="button" @click="addLifecycleGroup(current)">＋ 添加条件组</button>
        </template>
      </section>
    </div>
  </div>
</template>
<style scoped>
.lifecycle-global-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}.lifecycle-global-head h3{margin:0;font-size:14px}
.lifecycle-stage-tabs{display:flex;gap:24px;overflow:auto;border-bottom:1px solid var(--neutral-200)}.lifecycle-stage-tabs button{flex:none;padding:10px 0;border:0;border-bottom:2px solid transparent;background:transparent;font:inherit;font-size:14px;color:var(--neutral-500)}.lifecycle-stage-tabs button.active{border-bottom-color:var(--primary-600);color:var(--primary-600);font-weight:600}
.lifecycle-stage-panel{padding-top:16px}.lifecycle-summary-preview{margin:0 0 16px}
.lifecycle-condition-group{margin:12px 0;padding:14px 16px;border:1px solid var(--neutral-200);border-radius:12px;background:var(--neutral-50)}.lifecycle-group-caption{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px;font-size:12px;color:var(--text-secondary)}
.lifecycle-range-row{display:flex;align-items:flex-end;flex-wrap:wrap;gap:10px;margin-top:10px}.lifecycle-range-row .field{flex:0 1 132px;min-width:0;font-size:13px}.lifecycle-range-row .lifecycle-metric{flex-basis:190px}.lifecycle-range-row input,.lifecycle-range-row select{box-sizing:border-box;width:100%;height:32px;min-height:32px;padding:0 10px;border:1px solid var(--neutral-200);border-radius:12px;background:var(--surface);font:inherit}.lifecycle-range-row input{text-align:left}.lifecycle-range-unit,.lifecycle-range-separator{flex:none;line-height:32px;font-size:13px;color:var(--text-secondary)}.lifecycle-range-row .icon-btn{height:32px;width:32px;padding:0;font-size:22px}.lifecycle-range-row .icon-btn:disabled{opacity:.3;cursor:default}.lifecycle-range-error{flex-basis:100%;font-size:12px;color:var(--danger)}
.lifecycle-or{display:inline-flex;align-items:center;padding:4px 10px;border-radius:12px;color:var(--primary-700);background:var(--primary-50);font-size:12px}.lifecycle-add-group{margin-top:4px;border:1px dashed var(--primary-200);border-radius:12px;padding:7px 12px}
@media(max-width:580px){.lifecycle-range-row .lifecycle-metric{flex-basis:100%}.lifecycle-range-row .field{flex:1 1 90px}.lifecycle-stage-tabs{gap:16px}}
</style>
