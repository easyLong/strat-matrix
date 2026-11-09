<script>
import { formatDateTime } from '../../planningTime';
export default {
  props: {
    logs: {
      type: Array,
      required: true
    },
    loading: Boolean,
    error: String
  },
  computed: {
    formatDateTime() {
      return formatDateTime;
    }
  }
};
</script>
<template>
  <section class="plan-operation-timeline">
    <h3>操作记录</h3>
    <div v-if="loading" class="empty-state">正在读取操作记录…</div>
    <div v-else-if="error" class="detail-note" role="alert">{{ error }}</div>
    <ol v-else-if="logs.length"><li v-for="log in logs" :key="log.key"><div class="operation-title"><b>{{ log.action }}</b><time>{{ formatDateTime(log.createdAt) }}</time></div><p>{{ log.detail }}</p><small>操作方：{{ log.actor }}</small></li></ol>
    <div v-else class="empty-state">暂无操作记录</div>
  </section>
</template>
<style scoped>
.plan-operation-timeline h3{font-size:14px;margin:0 0 16px}.plan-operation-timeline ol{list-style:none;margin:0;padding:0 0 0 18px}.plan-operation-timeline li{position:relative;padding:0 0 20px 8px}.plan-operation-timeline li::before{position:absolute;left:-17px;top:6px;width:8px;height:8px;border:2px solid var(--primary-100);border-radius:50%;background:var(--primary-600);content:''}.plan-operation-timeline li:not(:last-child)::after{position:absolute;left:-12px;top:18px;bottom:-3px;width:1px;background:var(--neutral-200);content:''}.operation-title{display:flex;align-items:baseline;justify-content:space-between;gap:12px}.operation-title b{font-size:14px}.operation-title time,.plan-operation-timeline small{font-size:12px;color:var(--text-muted)}.plan-operation-timeline p{margin:7px 0;font-size:13px;line-height:22px;color:var(--text-secondary);overflow-wrap:anywhere}@media(max-width:580px){.operation-title{align-items:flex-start;flex-direction:column;gap:4px}}
</style>
