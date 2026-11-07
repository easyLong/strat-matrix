<script lang="ts">
import { defineComponent } from '../compat/composition'
export default defineComponent({
  name:'DateRangeFields',
  props:{ start:{type:String,default:''}, end:{type:String,default:''}, required:Boolean, disabled:Boolean },
})
</script>
<template><div class="date-range-fields"><label class="field"><span>开始时间 <em v-if="required" class="required-mark">✳</em></span><input :value="start" type="date" aria-label="开始时间" :max="end || undefined" :required="required" :disabled="disabled" @input="$emit('update:start',$event.target.value)" @keydown.enter.prevent="$emit('query')" /></label><label class="field"><span>截止时间 <em v-if="required" class="required-mark">✳</em></span><input :value="end" type="date" aria-label="截止时间" :min="start || undefined" :required="required" :disabled="disabled" @input="$emit('update:end',$event.target.value)" @keydown.enter.prevent="$emit('query')" /></label></div></template>
<style scoped>.date-range-fields{display:contents}.field{display:flex;min-width:0;flex-direction:column;gap:8px;font-size:14px}.field>span{white-space:nowrap}.field input{box-sizing:border-box;width:100%;min-width:0;height:32px;font:inherit;color:var(--text-primary,var(--neutral-900));background:var(--surface);border:1px solid var(--neutral-200);border-radius:12px;padding:0 10px}</style>
