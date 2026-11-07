<script lang="ts">
import DialogTitle from '../DialogTitle.vue';
import { defineComponent, type PropType } from '../../compat/composition';
import { onBeforeUnmount, ref, watch } from '../../compat/composition';
import { api } from '../../api';
import type { PeriodSummary } from '../../api/queries';
import type { AutoFailure } from '../../types';
import { downloadCsv } from '../../ui/csv';
import { canPlanning, requirePlanning } from '../../host/runtime';
export default defineComponent({
    props: { failurePeriod: { required: true, type: null as unknown as PropType<PeriodSummary> } },
    setup(props, context) {
        const emit = context.emit;
        const failureDetails = ref<AutoFailure[]>([]);
        const failureLoading = ref(false);
        const failureError = ref('');
        let request = 0;
        let controller: AbortController | undefined;
        watch(() => props.failurePeriod, async (period) => {
            const current = ++request;
            controller?.abort();
            controller = new AbortController();
            failureDetails.value = [];
            failureError.value = '';
            failureLoading.value = true;
            try {
                const rows = await api.resultFailures({
                    mode: 'cycle',
                    cycle_start: period.cycleStart,
                    cycle_end: period.cycleEnd,
                    batch_ids: period.batches.map(b => b.id),
                    page: 1,
                    page_size: 200,
                    filters: {}
                }, controller.signal);
                if (current === request)
                    failureDetails.value = rows;
            }
            catch (error) {
                if (current === request)
                    failureError.value = error instanceof Error ? error.message : '读取失败详情失败';
            }
            finally {
                if (current === request)
                    failureLoading.value = false;
            }
        }, {
            immediate: true
        });
        onBeforeUnmount(() => {
            ++request;
            controller?.abort();
        });
        function downloadFailureUms() {
            requirePlanning('results.export');
            const rows = failureDetails.value.filter(row => row.um_no);
            if (!rows.length)
                return;
            downloadCsv(`失败账号UM号_${props.failurePeriod.cycleStart}_${props.failurePeriod.cycleEnd}.csv`, [['属主UM号', '账号名称', '账号ID', '批次号', '失败原因'], ...rows.map(row => [row.um_no, row.account_name, row.account_id, row.batch_code, row.reason])]);
        }
        return {
            canPlanning,
            emit,
            failureDetails,
            failureLoading,
            failureError,
            downloadFailureUms
        };
    },
    components: {DialogTitle}
});
</script>
<template>
  <div class="drawer-mask" @click.self="emit('close')">
    <aside class="drawer failure-drawer" role="dialog" aria-modal="true" aria-labelledby="failure-detail-title">
      <div class="drawer-head">
        <DialogTitle id="failure-detail-title" :title="`失败详情（${failureDetails.length}）`" :context="`${failurePeriod.cycleStart} 至 ${failurePeriod.cycleEnd}`" />
        <button class="icon-btn" type="button" aria-label="关闭失败详情" @click="emit('close')">×</button>
      </div>
      <div class="drawer-body">

        <div class="failure-detail-toolbar">
          <div><b>失败账号</b><span>{{ failureDetails.length }} 个</span></div>
        </div>
        <p class="failure-guidance">以下账号未完成本周期策划，可转人工策划补充。</p>
        <div v-if="failureLoading" class="empty-state">正在读取失败详情…</div>
        <div v-else-if="failureError" class="banner error-banner" role="alert">{{ failureError }}</div>
        <div v-else-if="failureDetails.length === 0" class="empty-state">暂无失败账号明细</div>
        <div v-else class="table-wrap failure-table-wrap">
          <table class="failure-detail-table">
            <thead><tr><th>账号</th><th>属主 UM 号</th><th>批次</th><th>失败原因</th></tr></thead>
            <tbody><tr v-for="(item, index) in failureDetails" :key="`${item.batch_code}-${item.account_id ?? index}`">
              <td><div class="failure-account"><b>{{ item.account_name }}</b><small>{{ item.account_id || '批次级异常' }}</small></div></td>
              <td>{{ item.um_no || '—' }}</td>
              <td>{{ item.batch_code }}</td>
              <td>{{ item.reason || '未提供失败原因' }}</td>
            </tr></tbody>
          </table>
        </div>
      </div>
      <div class="drawer-foot failure-footer"><button class="btn" type="button" @click="emit('close')">关闭</button><button v-if="canPlanning('results.export')" class="btn primary" type="button" :disabled="failureLoading || !failureDetails.some(item => item.um_no)" @click="downloadFailureUms">导出失败账号</button></div>
    </aside>
  </div>
</template>
<style scoped>

.failure-drawer{width:min(860px,96vw)}
.failure-detail-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 16px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--neutral-50)}
.failure-detail-toolbar>div{display:flex;align-items:baseline;gap:10px}.failure-detail-toolbar b{color:var(--neutral-800);font-size:14px}.failure-detail-toolbar span{color:var(--danger);font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}
.failure-guidance{margin:12px 0 16px;color:var(--neutral-500);font-size:13px;line-height:1.6}
.failure-table-wrap{max-height:min(560px,62vh);overflow:auto}.failure-detail-table{min-width:680px}.failure-account{display:flex;flex-direction:column;gap:3px}.failure-account b{color:var(--neutral-700);font-size:13px}.failure-account small{color:var(--neutral-400);font-size:11px}
@media(max-width:980px){}

</style>
