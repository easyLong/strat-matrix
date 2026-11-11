<script>
export default {
  props: {
    completed: {
      required: true,
      type: Number
    },
    total: {
      required: true,
      type: Number
    },
    display: {
      required: false,
      type: String,
      default: 'progress'
    }
  },
  computed: {
    description() {
      return `完成内容生产 ${this.completed} 个账号 / 共 ${this.total} 个账号`;
    },
    statusLabel() {
      if (this.total > 0 && this.completed >= this.total) return '已完成';
      if (this.completed > 0) return '生成中';
      return '待生成';
    },
    statusTone() {
      return this.statusLabel === '已完成' ? 'status-completed' : this.statusLabel === '生成中' ? 'status-processing' : 'status-waiting';
    }
  }
};
</script>

<template>
  <span v-if="display === 'status'" :class="['content-status', statusTone]" :title="description" :aria-label="`${statusLabel}（${completed}/${total}）`">
    <b>{{ statusLabel }}</b><span>（{{ completed }}/{{ total }}）</span>
  </span>
  <span v-else class="content-progress" :title="description" :aria-label="description">
    <span :class="{ completed: completed > 0 }">{{ completed }}</span>
    <span class="separator" aria-hidden="true">/</span>
    <span class="total">{{ total }}</span>
  </span>
</template>

<style scoped>
.content-progress{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;color:var(--neutral-400);font-variant-numeric:tabular-nums}
.completed{color:var(--success);font-weight:600}
.separator{color:var(--neutral-300);font-weight:400}
.total{color:var(--neutral-700);font-weight:500}
.content-status{display:inline-flex;align-items:center;gap:5px;white-space:nowrap;font-variant-numeric:tabular-nums}.content-status b{font-weight:600}.content-status>span{color:var(--text-secondary);font-weight:500}.status-completed b{color:var(--success)}.status-processing b{color:var(--processing)}.status-waiting b{color:var(--warning)}
</style>
