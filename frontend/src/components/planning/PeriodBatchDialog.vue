<script>
import { bindPageActivity } from "../../services/pageActivity";
import { formatDateTime } from '../../planningTime';
import { statusTone } from '../../ui/status';
import ContentProgress from '../ContentProgress.vue';
import PlanningExport from '../PlanningExport.vue';
import DialogTitle from '../DialogTitle.vue';
export default {
  props: {
    period: {
      type: Object,
      required: true
    }
  },
  components: {
    ContentProgress,
    PlanningExport,
    DialogTitle
  },
  data() {
    return {
      opener: null,
      active: null
    };
  },
  computed: {
    dialog: {
      cache: false,
      get() {
        return this.$refs.dialog || null;
      }
    },
    formatDateTime() {
      return formatDateTime;
    },
    statusTone() {
      return statusTone;
    }
  },
  methods: {
    keepFocus(event) {
      const controls = [...(this.dialog?.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href],[tabindex="0"]') || [])].filter(el => el.getClientRects().length);
      const first = controls[0],
        last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
  },
  created() {
    this.active = bindPageActivity(this, () => {
      this.opener = document.activeElement;
      void this.$nextTick(() => {
        if (this.active.active) this.dialog?.querySelector('button')?.focus();
      });
    }, () => {
      if (this.dialog?.contains(document.activeElement) && this.opener?.isConnected) this.opener.focus();
    });
  }
};
</script>
<template><BodyPortal><div class="drawer-mask period-batches-mask" @click.self="$emit('close')"><section ref="dialog" class="period-batches-dialog" @keydown.esc.stop="$emit('close')" @keydown.tab="keepFocus" role="dialog" aria-modal="true" aria-label="周期批次列表"><div class="drawer-head"><DialogTitle title="批次列表" :context="`${period.cycleStart} 至 ${period.cycleEnd}`" /><button class="icon-btn" type="button" aria-label="关闭批次列表" @click="$emit('close')">×</button></div><div class="period-batches-summary"><span class="tag blue">{{ period.batches.length }} 个批次</span><span>{{ period.accountCount }} 个账号</span></div><div class="period-batch-panel"><div class="table-wrap"><table>
                      <thead><tr><th>批次</th><th>策划方式</th><th>批次周期</th><th>账号数</th><th>完成数</th><th>失败数</th><th>选题数</th><th>策划状态</th><th title="完成内容生产的账号数 / 总账号数">内容状态</th><th>更新时间</th><th>操作</th></tr></thead>
                      <tbody><tr v-for="batch in period.batches" :key="batch.id">
                        <td><div class="account-name-cell"><b>{{ batch.task_name || '—' }}</b><small>ID {{ batch.batch_code }}</small></div></td>
                        <td>{{ batch.plan_type === 'manual' ? '人工策划' : 'AI 自动策划' }}</td>
                        <td>{{ batch.cycle_start }} 至 {{ batch.cycle_end }}</td>
                        <td>{{ batch.account_count }}</td>
                        <td class="batch-count" :class="{ completed: batch.completed_count > 0 }">{{ batch.completed_count }}</td>
                        <td class="batch-count" :class="{ failed: batch.failed_count > 0 }">{{ batch.failed_count }}</td>
                        <td>{{ batch.topic_count }}</td>
                        <td><span :class="['tag', statusTone(batch.planning_status)]">{{ batch.planning_status || batch.status }}</span></td>
                        <td><ContentProgress display="status" :completed="batch.content_completed_account_count" :total="batch.account_count" /></td>
                        <td>{{ formatDateTime(batch.updated_at || batch.created_at) }}</td>
                        <td><div class="period-actions"><button class="text-btn" type="button" @click="$emit('open-batch', batch)">查看策划</button><PlanningExport inline :batches="[batch]" :filename="`策划明细_${batch.batch_code}.xlsx`" /></div></td>
                      </tr></tbody>
                    </table></div></div><div class="drawer-foot"><button class="btn" type="button" @click="$emit('close')">关闭</button></div></section></div></BodyPortal></template>
<style scoped>.period-batches-dialog{display:flex;flex-direction:column;width:min(1280px,calc(100vw - 48px));max-height:calc(100dvh - 64px);margin:auto;border:1px solid var(--neutral-200);border-radius:12px;background:var(--surface);box-shadow:var(--shadow-4);overflow:hidden}.period-batches-mask{display:flex;align-items:center;justify-content:center;padding:24px}.period-batches-summary{display:flex;align-items:center;gap:12px;padding:12px 20px;font-size:13px}.period-batch-panel{min-height:0;overflow:auto;padding:0 20px 16px}.table-wrap{overflow:auto;max-height:min(60dvh,560px)}table{min-width:1080px;width:100%}.period-actions{display:flex;align-items:center;gap:12px;white-space:nowrap}.drawer-foot{display:flex;justify-content:flex-end}</style>
