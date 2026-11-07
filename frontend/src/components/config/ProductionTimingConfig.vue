<script lang="ts">
import { computed, defineComponent, type PropType } from '../../compat/composition';
import HoverHint from '../HoverHint.vue';
import type { ProductionLeadDays, ProductionTopicType } from '../../types';
import { productionLeadLabel, productionTopicTypes } from '../../ui/productionTiming';
export default defineComponent({
  components: { HoverHint },
  props: {
    value: { type: Object as PropType<ProductionLeadDays | null>, required: false },
    readonly: { type: Boolean, default: false },
  },
  setup(props, { emit }) {
    function change(key: ProductionTopicType, event: Event) {
      if (props.readonly) return;
      const raw = (event.target as HTMLInputElement).value;
      emit('input', { ...props.value, [key]: raw === '' ? null : Number(raw) });
    }
    const isInvalid = (days?: number | null) => days != null && (!Number.isInteger(days) || days < 0 || days > 365);
    return { change, isInvalid, productionLeadLabel, productionTopicTypes,
      leadDays: computed(() => props.value || {}) };
  },
});
</script>
<template>
  <section class="production-timing-config" aria-label="内容生产时间">
    <div class="production-timing-title"><h3>内容生产时间</h3><HoverHint text="T 为投放日期。T−3 表示投放前 3 个自然日开始生产，T−0 表示投放当天。仅以已确定的投放日期为基准。" aria-label="内容生产时间说明" /></div>
    <div class="production-timing-grid">
      <div v-for="type in productionTopicTypes" :key="type.key" class="production-timing-item">
        <span class="production-timing-label">{{ type.label }}</span>
        <b v-if="readonly" :class="{ unset: leadDays[type.key] == null }">{{ productionLeadLabel(leadDays[type.key]) }}</b>
        <label v-else class="production-timing-input"><span>T−</span><input :value="leadDays[type.key] == null ? '' : leadDays[type.key]" :aria-label="`${type.label}生产提前天数`" type="number" inputmode="numeric" min="0" max="365" step="1" placeholder="天数" :aria-invalid="isInvalid(leadDays[type.key]) || undefined" @input="change(type.key, $event)" /><span>天</span></label>
      </div>
    </div>
  </section>
</template>
<style scoped>
.production-timing-config{margin-top:20px;padding-top:16px;border-top:1px solid var(--neutral-200)}
.production-timing-title{display:flex;align-items:center;gap:6px;margin-bottom:12px}.production-timing-title h3{margin:0;font-size:14px;font-weight:600;line-height:22px}
.production-timing-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.production-timing-item{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border:1px solid var(--neutral-200);border-radius:6px;background:var(--neutral-50)}
.production-timing-label{color:var(--neutral-600);font-size:13px;white-space:nowrap}.production-timing-item b{color:var(--neutral-800);font-size:13px;font-weight:500;white-space:nowrap}.production-timing-item b.unset{color:var(--neutral-400);font-weight:400}
.production-timing-input{display:flex;align-items:center;gap:8px;margin:0;font-size:13px;color:var(--neutral-600)}.production-timing-input input{box-sizing:border-box;width:64px;height:32px;padding:0 8px;border:1px solid var(--neutral-200);border-radius:6px;background:var(--surface);text-align:center;font-variant-numeric:tabular-nums;appearance:textfield;-moz-appearance:textfield}.production-timing-input input::-webkit-inner-spin-button,.production-timing-input input::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}.production-timing-input input[aria-invalid=true]{border-color:var(--danger)}
@media(max-width:1050px){.production-timing-grid{grid-template-columns:1fr}.production-timing-item{justify-content:flex-start}.production-timing-label{min-width:76px}}
</style>
