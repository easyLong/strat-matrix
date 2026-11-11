<script>
import PlanningDateInput from './PlanningDateInput.vue';
export default {
  name: 'DateRangeFields',
  components: { PlanningDateInput },
  computed: {
    startInputId() { return `planning-start-${this._uid}`; },
    endInputId() { return `planning-end-${this._uid}`; },
  },
  props: {
    start: {
      type: String,
      default: ''
    },
    end: {
      type: String,
      default: ''
    },
    required: Boolean,
    disabled: Boolean
  }
};
</script>
<template><div class="date-range-fields"><label class="field" :for="startInputId"><span>开始时间 <em v-if="required" class="required-mark">✳</em></span><PlanningDateInput :value="start" :input-id="startInputId" :max="end" :required="required" :disabled="disabled" @input="$emit('update:start',$event)" @enter="$emit('query')" /></label><label class="field" :for="endInputId"><span>截止时间 <em v-if="required" class="required-mark">✳</em></span><PlanningDateInput :value="end" :input-id="endInputId" :min="start" :required="required" :disabled="disabled" @input="$emit('update:end',$event)" @enter="$emit('query')" /></label></div></template>
<style scoped>.date-range-fields{display:contents}.field{display:flex;min-width:0;flex-direction:column;gap:8px;font-size:14px}.field>span{white-space:nowrap}.field input{box-sizing:border-box;width:100%;min-width:0;height:32px;font:inherit;color:var(--text-primary,var(--neutral-900));background:var(--surface);border:1px solid var(--neutral-200);border-radius:12px;padding:0 10px}</style>
