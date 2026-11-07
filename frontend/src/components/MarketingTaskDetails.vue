<script lang="ts">
import DialogTitle from './DialogTitle.vue';
import { useActivePage } from '../composables/useActivePage';
import { defineComponent, type PropType } from '../compat/composition';
import { computed, onBeforeUnmount, onMounted, ref } from '../compat/composition';
import AccountTypeBadge from './AccountTypeBadge.vue';
import ListPagination from './ListPagination.vue';
import MarketingTopicTable from './MarketingTopicTable.vue';
import type { AccountOption, ManualTaskSummary, TopicOption } from '../types';
export default defineComponent({
    props: { details: { required: true, type: Object as PropType<{
                task: ManualTaskSummary;
                accounts: AccountOption[];
                topics: TopicOption[];
            }> } },
    setup(props, context) {
        const emit = context.emit;
        const page = ref(1);
        const size = ref(20);
        const panel = ref<HTMLElement | null>(null);
        const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        const rows = computed(() => props.details.accounts.slice((page.value - 1) * size.value, page.value * size.value));
        const awaitingExternalAllocation = computed(() => (props.details.task.allocation_count || 0) > 0 && props.details.accounts.length === 0);
        function keyboard(event: KeyboardEvent) {
            if (event.key === 'Escape') {
                event.preventDefault();
                emit('close');
            }
            if (event.key !== 'Tab')
                return;
            const focusable = panel.value?.querySelectorAll<HTMLElement>('button:not(:disabled),select');
            if (!focusable?.length)
                return;
            const first = focusable[0]!, last = focusable[focusable.length - 1]!;
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            }
            else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }
        useActivePage(() => {
            panel.value?.querySelector('button')?.focus();
            document.addEventListener('keydown', keyboard);
        }, () => {
            document.removeEventListener('keydown', keyboard);
            if (previousFocus?.isConnected && previousFocus.getClientRects().length) previousFocus.focus();
        });
        return {
            emit,
            page,
            size,
            panel,
            rows,
            awaitingExternalAllocation
        };
    },
    components: {DialogTitle, AccountTypeBadge, ListPagination, MarketingTopicTable}
});
</script>

<template>
  <BodyPortal>
    <div class="marketing-detail-mask" @click.self="emit('close')">
      <section ref="panel" class="marketing-detail" role="dialog" aria-modal="true" aria-labelledby="marketing-detail-title">
        <header><div><h2 id="marketing-detail-title">营销策划详情</h2><small>{{ details.task.task_name }} · {{ details.task.task_code }}</small></div><button class="btn" type="button" @click="emit('close')">返回任务列表</button></header>

        <div class="marketing-detail-counts"><template v-if="awaitingExternalAllocation"><span>生成内容数量 <b>{{ details.task.allocation_count }}</b> 条</span><span>账号分配 <b>待外部系统</b></span></template><template v-else><span>账号数 <b>{{ details.accounts.length }}</b></span><span>每账号 <b>{{ details.task.content_per_account }}</b> 条</span><span>总生产数量 <b>{{ details.task.content_total_count }}</b> 条</span></template><span class="tag gray">{{ details.task.status }}</span></div>
        <template v-if="details.accounts.length"><div class="table-wrap"><table><thead><tr><th>账号昵称</th><th>账号 ID</th><th>属主 UM 号</th><th>账号类型</th></tr></thead><tbody><tr v-for="account in rows" :key="account.account_id"><td>{{ account.account_name }}</td><td>{{ account.account_id }}</td><td>{{ account.um_no || '—' }}</td><td><AccountTypeBadge type="认证" /></td></tr></tbody></table></div><ListPagination :page.sync="page" :page-size.sync="size" :total="details.accounts.length" unit="个账号" /></template>
        <section><h3>选题</h3><div v-if="details.topics.length" class="table-wrap"><MarketingTopicTable :topics="details.topics" /></div><div v-else class="empty-state">暂无选题</div></section>
      </section>
    </div>
  </BodyPortal>
</template>

<style scoped>
.marketing-detail-mask{position:fixed;inset:0;z-index:100;display:flex;justify-content:flex-end;background:var(--mask)}
.marketing-detail{box-sizing:border-box;width:min(900px,100%);padding:24px;background:var(--surface);overflow:auto;box-shadow:var(--shadow-4)}
header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}h2{margin:0 0 8px;font-size:18px}small{color:var(--neutral-500);overflow-wrap:anywhere}header button{flex:none}.marketing-detail-counts{display:flex;flex-wrap:wrap;align-items:center;gap:24px;margin:24px 0;padding:16px;background:var(--neutral-50);border-radius:8px;font-size:13px}.marketing-detail-counts b{color:var(--primary-600);font-size:20px;font-variant-numeric:tabular-nums}.table-wrap{max-height:50vh;overflow:auto}table{min-width:600px}h3{font-size:14px}section>section{margin-top:24px}
</style>
