<script lang="ts">
import { defineComponent, type PropType } from '../../compat/composition';
import { computed } from '../../compat/composition';
import type { AccountPlanRecord } from '../../types';
import { daysFor, topicTypeLabel, sourceLabel, sourceHint, type PlanningWeek } from '../../ui/planningCalendar';
import { statusTone } from '../../ui/status';
import { productionStatusLabel } from '../../ui/slotContentStatus';
export default defineComponent({
    props: { week: { required: true, type: null as unknown as PropType<PlanningWeek> },
        compactSource: { required: false, type: Boolean as PropType<boolean>, default: false },
        showBatch: { required: false, type: Boolean as PropType<boolean>, default: true },
        showTopicType: { required: false, type: Boolean as PropType<boolean>, default: false } },
    setup(props, context) {
        const emit = context.emit;
        const days = computed(() => daysFor(props.week));
        return {
            topicTypeLabel,
            sourceLabel,
            sourceHint,
            statusTone,
            productionStatusLabel,
            emit,
            days
        };
    }
});
</script>
<template>
  <div class="planning-week-wrap"><div class="planning-week-grid">
    <section v-for="day in days" :key="day.date" class="planning-day">
      <header><div><b>{{ day.label }}</b><small>{{ day.weekday }}</small></div><span>{{ day.items.length }} 条</span></header>
      <div v-if="day.items.length" class="planning-day-items">
        <button v-for="item in day.items" :key="item.id" type="button" class="planning-plan-card navigable" :aria-label="`查看计划详情：${item.topic_title || '待确定选题'}`" @click="emit('select',item)">
          <div class="account-week-plan-tags">
            <span v-if="compactSource" :class="['tag','gray','planning-source-badge',item.plan_type==='manual'?'source-manual':'source-ai']" :data-source-hint="sourceHint(item)" :aria-label="sourceHint(item)" tabindex="0">{{ sourceLabel(item) }}</span>
            <span v-else class="tag gray">{{ item.plan_type==='manual'?'人工策划':'自动策划' }}</span>
            <span :class="['tag',statusTone(productionStatusLabel(item))]">{{ productionStatusLabel(item) }}</span>
          </div>
          <b>{{ item.topic_title || '待确定选题' }}</b>
          <small>{{ item.content_type || '—' }}<template v-if="showTopicType"> · {{ topicTypeLabel(item) }}</template></small>
          <span v-if="showBatch" class="planning-plan-batch">{{ item.batch_code }}</span>
        </button>
      </div>
      <div v-else class="planning-day-empty">暂无计划</div>
    </section>
  </div></div>
</template>
<style scoped>

.planning-week-wrap{padding:12px 14px 14px;border-top:1px solid var(--neutral-100);background:var(--neutral-50);overflow-x:auto}.planning-week-grid{display:grid;grid-template-columns:repeat(7,minmax(150px,1fr));gap:8px;min-width:1100px}.planning-day{overflow:hidden;min-height:166px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface)}.planning-day>header{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:9px 10px;border-bottom:1px solid var(--neutral-100);background:var(--neutral-50)}.planning-day>header>div{display:flex;align-items:baseline;gap:6px}.planning-day>header b{color:var(--neutral-700);font-size:12px}.planning-day>header small,.planning-day>header span{color:var(--neutral-400);font-size:10px}.planning-day-items{display:grid;gap:7px;padding:8px}.planning-plan-card{position:relative;display:flex;flex-direction:column;align-items:flex-start;gap:6px;width:100%;padding:9px;border:1px solid var(--neutral-200);border-radius:7px;background:var(--surface);color:inherit;text-align:left}.planning-plan-card.navigable{cursor:pointer;transition:border-color .14s ease,box-shadow .14s ease,transform .14s ease}.planning-plan-card.navigable:hover{border-color:var(--primary-200);box-shadow:0 4px 12px rgba(15,23,42,.05);transform:translateY(-1px)}.planning-plan-card>b{display:-webkit-box;overflow:hidden;color:var(--neutral-700);font-size:12px;line-height:18px;-webkit-line-clamp:2;-webkit-box-orient:vertical}.planning-plan-card>small{color:var(--neutral-400);font-size:10px}.planning-plan-batch{color:var(--neutral-400);font-size:9px}.planning-day-empty{display:grid;place-items:center;min-height:108px;color:var(--neutral-300);font-size:11px}
.planning-source-badge{display:inline-flex!important;align-items:center;gap:4px;border:1px solid transparent!important;font-weight:600!important}.planning-source-badge::before{width:5px;height:5px;border-radius:50%;background:currentColor;content:''}.planning-source-badge.source-ai{border-color:#bfdbfe!important;background:#eff6ff!important;color:#2563eb!important}.planning-source-badge.source-manual{border-color:#fed7aa!important;background:#fff7ed!important;color:#c2410c!important}
@media(max-width:580px){.planning-week-wrap{padding:10px 8px 12px}}

</style>
