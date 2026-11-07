<script lang="ts">
import { defineComponent, type PropType } from '../compat/composition';
import { computed, nextTick, onBeforeUnmount, onMounted, ref, toRef, watch } from '../compat/composition';
import { useRouter } from '../compat/router';
import ManualAccountStep from '../components/manual/ManualAccountStep.vue';
import { useManualAccountSelection } from '../composables/useManualAccountSelection';
import ManualTopicStep from '../components/manual/ManualTopicStep.vue';
import { useManualTopicSelection } from '../composables/useManualTopicSelection';
import ManualTaskList from '../components/manual/ManualTaskList.vue';
import MarketingTaskDetails from '../components/MarketingTaskDetails.vue';
import { usePageBreadcrumbs } from '../composables/usePageBreadcrumbs';
import { api } from '../api';
import ManualConfirmationLists from '../components/ManualConfirmationLists.vue';
import { usePlanningStore } from '../store';
import type { AccountOption, ManualTaskSummary, TopicOption } from '../types';
import { createRequestId } from '../ui/requestId';
import { beijingDate } from '../ui/manualTopics';
export default defineComponent({
    setup(props, context) {
        const store = usePlanningStore();
        const router = useRouter();
        const mode = computed<'list' | 'create'>({
            get: () => store.manualCreating ? 'create' : 'list',
            set: value => {
                store.manualCreating = value === 'create';
            }
        });
        const step = ref(1);
        const busy = ref(false);
        const stepperRef = ref<HTMLElement | null>(null);
        const taskName = ref('');
        const contentMode = ref<'marketing' | 'non_marketing'>('non_marketing');
        const isMarketing = computed(() => contentMode.value === 'marketing');
        const allocationCount = ref<number | ''>('');
        const marketingRequestId = ref('');
        const marketingDetails = ref<Awaited<ReturnType<typeof api.marketingTaskDetails>> | null>(null);
        const workflowSteps = computed(() => isMarketing.value ? [{
                number: 1,
                label: '创建策划'
            }, {
                number: 2,
                label: '选择选题'
            }, {
                number: 3,
                label: '确认策划'
            }] : [{
                number: 1,
                label: '创建策划'
            }, {
                number: 2,
                label: '选择账号'
            }, {
                number: 3,
                label: '选择选题'
            }, {
                number: 4,
                label: '确认策划'
            }]);
        const topicStepNumber = computed(() => isMarketing.value ? 2 : 3);
        const submitStepNumber = computed(() => isMarketing.value ? 3 : 4);
        usePageBreadcrumbs(() => {
            const toList = () => {
                mode.value = 'list';
                marketingDetails.value = null;
                error.value = '';
            };
            const parents = [{
                    label: '人工策划',
                    action: toList
                }, {
                    label: '策划任务列表',
                    action: toList
                }];
            if (mode.value === 'create')
                return [...parents, {
                        label: '新建人工策划',
                        action: () => returnToStep(1)
                    }, {
                        label: workflowSteps.value.find(item => item.number === step.value)?.label || '创建策划'
                    }];
            return marketingDetails.value ? [...parents, {
                    label: '营销策划详情'
                }] : parents;
        });
        const validAllocationCount = computed(() => Number.isInteger(allocationCount.value) && Number(allocationCount.value) >= 1 && Number(allocationCount.value) <= 1000);
        const publishDate = ref('');
        const today = ref(beijingDate());
        let validityTimer: ReturnType<typeof setInterval> | undefined;
        onMounted(() => { validityTimer = setInterval(() => { today.value = beijingDate(); }, 30000); });
        const accounts = ref<AccountOption[]>([]);
        const topics = ref<TopicOption[]>([]);
        watch([taskName, allocationCount], () => {
            marketingRequestId.value = createRequestId();
        }, {
            flush: 'sync'
        });
        const catalogLoading = ref(false);
        let catalogRequest = 0;
        const error = ref('');
        watch(allocationCount, () => {
            if (validAllocationCount.value && error.value === '请输入 1 至 1000 之间的生成内容数量')
                error.value = '';
        });
        const notice = ref('');
        const accountSelection = useManualAccountSelection({
            accounts,
            publishDate,
            isMarketing,
            databaseReady: toRef(store, 'databaseReady'),
            error,
            notice,
            fetchAvailability: api.manualAccountAvailability
        });
        const { sampledIds, selectedAccounts, targetCount, accountReview, availabilityReady, availabilityError, loadAccountAvailability, accountSelectionMode, importDataRowCount, accountPage, accountListRef } = accountSelection;
        const eligibilityNotice = ref('');
        const topicReview = ref(false);
        const topicSelection = useManualTopicSelection({
            topics,
            isMarketing,
            publishDate,
            today,
            topicReview,
            error
        });
        const { selectedTopicIds, selectedTopics, topicPage, topicListRef } = topicSelection;
        watch(selectedTopicIds, () => {
            marketingRequestId.value = createRequestId();
        }, {
            flush: 'sync'
        });
        async function revealStepProgress() {
            await nextTick();
            const stepper = stepperRef.value;
            stepper?.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
            const activeStep = stepper?.querySelector<HTMLElement>('.manual-step.active');
            if (stepper && activeStep && stepper.scrollWidth > stepper.clientWidth) {
                stepper.scrollTo({
                    left: Math.max(0, activeStep.offsetLeft - stepper.offsetLeft - 16),
                    behavior: 'smooth'
                });
            }
        }
        async function resetSelectionListScroll(target: 'accounts' | 'topics') {
            await nextTick();
            const list = target === 'accounts' ? accountListRef.value : topicListRef.value;
            if (list) {
                list.scrollTop = 0;
                list.scrollLeft = 0;
            }
        }
        const canSubmit = computed(() => topicSelection.selectionValid.value && (isMarketing.value ? store.databaseReady && !busy.value && taskName.value.trim() !== '' && selectedTopicIds.value.length === 1 && validAllocationCount.value : store.databaseReady && availabilityReady.value && !busy.value && taskName.value.trim() !== '' && sampledIds.value.length > 0 && selectedTopicIds.value.length > 0 && publishDate.value !== ''));
        watch(contentMode, () => {
            accountSelection.reset();
            topicSelection.reset();
            topicReview.value = false;
            marketingRequestId.value = createRequestId();
        });
        async function loadCatalog() {
            const request = ++catalogRequest;
            catalogLoading.value = true;
            try {
                const [accountRows, topicRows] = await Promise.all([api.accounts(), api.topics()]);
                if (request !== catalogRequest)
                    return;
                accounts.value = accountRows;
                topics.value = topicRows;
            }
            catch (exc) {
                if (request === catalogRequest)
                    error.value = exc instanceof Error ? exc.message : '读取账号和选题失败';
            }
            finally {
                if (request === catalogRequest)
                    catalogLoading.value = false;
            }
        }
        async function openTaskDetails(task: ManualTaskSummary) {
            // 已生成正式批次的任务统一复用策划结果中的批次策划详情。
            if (task.batch_id) {
                void router.push({
                    path: '/results',
                    query: {
                        batch: String(task.batch_id),
                        from: 'manual'
                    }
                });
                return;
            }
            if (task.content_mode === 'marketing') {
                try {
                    marketingDetails.value = await api.marketingTaskDetails(task.task_code);
                }
                catch (exc) {
                    error.value = exc instanceof Error ? exc.message : '读取营销策划失败';
                }
                return;
            }
            if (!task.batch_id)
                return;
            void router.push({
                path: '/results',
                query: {
                    batch: String(task.batch_id),
                    plan_type: 'manual',
                    from: 'manual'
                }
            });
        }
        watch([() => store.databaseReady, mode], ([ready, current]) => {
            if (ready && current === 'create')
                void loadCatalog();
            else {
                catalogRequest++;
                catalogLoading.value = false;
            }
        }, {
            immediate: true
        });
        onBeforeUnmount(() => {
            if (validityTimer !== undefined) clearInterval(validityTimer);
            catalogRequest++;
            store.manualCreating = false;
        });
        function startCreate() {
            contentMode.value = 'non_marketing';
            allocationCount.value = '';
            marketingRequestId.value = createRequestId();
            publishDate.value = '';
            step.value = 1;
            taskName.value = '';
            accountSelection.reset();
            topicSelection.reset();
            accountReview.value = false;
            topicReview.value = false;
            error.value = '';
            notice.value = '';
            eligibilityNotice.value = '';
            mode.value = 'create';
        }
        function returnToStep(next: number) {
            if (next >= step.value || busy.value)
                return;
            step.value = next;
            if (!isMarketing.value && next <= 2)
                accountReview.value = false;
            if (next <= topicStepNumber.value)
                topicReview.value = false;
            void revealStepProgress();
        }
        function savePlanStep() {
            error.value = '';
            if (!taskName.value.trim()) {
                error.value = '请输入任务名称';
                return;
            }
            if (!isMarketing.value && !publishDate.value) {
                error.value = '请选择投放日期';
                return;
            }
            step.value = 2;
            void revealStepProgress();
        }
        async function saveAccountStep() {
            error.value = '';
            if (!taskName.value.trim()) {
                error.value = '请输入任务名称';
                return;
            }
            if (!isMarketing.value && !publishDate.value) {
                error.value = '请选择投放日期';
                return;
            }
            if (accountSelectionMode.value === 'filter') {
                if (targetCount.value === '') {
                    error.value = '请输入计划账号数量';
                    return;
                }
                if (!Number.isInteger(targetCount.value) || targetCount.value < 1 || targetCount.value > 1000) {
                    error.value = '计划账号数量须为 1 至 1000 之间的整数';
                    return;
                }
            }
            else if (accountSelectionMode.value === 'upload') {
                if (!importDataRowCount.value) {
                    error.value = '请先导入账号模板';
                    return;
                }
                targetCount.value = importDataRowCount.value;
            }
            if (!sampledIds.value.length) {
                error.value = '请先选择账号';
                return;
            }
            if (!(await loadAccountAvailability()))
                return;
            if (!sampledIds.value.length) {
                error.value = '所选账号当日已手动策划，请重新选择';
                return;
            }
            accountPage.value = 1;
            accountReview.value = true;
            void resetSelectionListScroll('accounts');
        }
        function saveTopicStep() {
            error.value = '';
            if (!topicSelection.validateSelection()) return;
            if (!selectedTopicIds.value.length || isMarketing.value && selectedTopicIds.value.length !== 1) {
                error.value = isMarketing.value ? '请选择一个选题' : '请至少选择一个选题';
                return;
            }
            if (isMarketing.value && !validAllocationCount.value) {
                error.value = '请输入 1 至 1000 之间的生成内容数量';
                return;
            }
            topicPage.value = 1;
            topicReview.value = true;
            void resetSelectionListScroll('topics');
        }
        function confirmAccountReview() {
            if (!availabilityReady.value || !sampledIds.value.length) {
                accountReview.value = false;
                error.value = '请重新确认可策划账号后再继续';
                return;
            }
            accountReview.value = true;
            step.value = 3;
            void revealStepProgress();
        }
        function confirmTopicReview() {
            if (!topicSelection.validateSelection()) return;
            if (!selectedTopicIds.value.length || isMarketing.value && selectedTopicIds.value.length !== 1) {
                topicReview.value = false;
                error.value = isMarketing.value ? '请选择一个选题' : '请选择至少一个选题';
                return;
            }
            if (isMarketing.value && !validAllocationCount.value) {
                topicReview.value = false;
                error.value = '请输入 1 至 1000 之间的生成内容数量';
                return;
            }
            topicReview.value = true;
            step.value = submitStepNumber.value;
            error.value = '';
            void revealStepProgress();
        }
        async function submit() {
            if (!topicSelection.validateSelection()) return;
            if (!canSubmit.value)
                return;
            busy.value = true;
            error.value = '';
            notice.value = '';
            eligibilityNotice.value = '';
            try {
                if (isMarketing.value) {
                    await api.createMarketingTask({
                        request_id: marketingRequestId.value,
                        task_name: taskName.value.trim(),
                        topic_id: selectedTopicIds.value[0]!,
                        allocation_count: Number(allocationCount.value)
                    });
                    mode.value = 'list';
                    notice.value = '营销策划已提交';
                    return;
                }
                const selectedCount = sampledIds.value.length;
                if (!(await loadAccountAvailability()))
                    return;
                if (sampledIds.value.length !== selectedCount) {
                    step.value = 2;
                    error.value = '部分账号当日已手动策划，已移除，请重新确认账号数量';
                    return;
                }
                const preview = await api.previewManual({
                    content_mode: 'non_marketing',
                    task_name: taskName.value.trim(),
                    publish_date: publishDate.value,
                    account_ids: sampledIds.value,
                    target_count: selectedCount,
                    topic_ids: selectedTopicIds.value,
                    note: ''
                });
                await api.submitManualPreview(preview.preview_id);
                notice.value = '手动策划已提交，当前状态：生成中';
                mode.value = 'list';
            }
            catch (exc) {
                error.value = exc instanceof Error ? exc.message : '提交手动策划失败';
                if (error.value.includes('不具备所选营销选题资格'))
                    eligibilityNotice.value = error.value;
            }
            finally {
                busy.value = false;
            }
        }
        function closeEligibilityNotice(returnToSelection = false) {
            eligibilityNotice.value = '';
            if (returnToSelection) {
                error.value = '';
                accountReview.value = false;
                topicReview.value = false;
                step.value = 1;
                void revealStepProgress();
            }
        }
        return {
            store,
            mode,
            step,
            busy,
            stepperRef,
            taskName,
            contentMode,
            isMarketing,
            allocationCount,
            marketingDetails,
            workflowSteps,
            topicStepNumber,
            submitStepNumber,
            publishDate,
            catalogLoading,
            error,
            notice,
            accountSelection,
            selectedAccounts,
            targetCount,
            availabilityError,
            eligibilityNotice,
            topicReview,
            topicSelection,
            selectedTopics,
            canSubmit,
            openTaskDetails,
            startCreate,
            returnToStep,
            savePlanStep,
            saveAccountStep,
            saveTopicStep,
            confirmAccountReview,
            confirmTopicReview,
            submit,
            closeEligibilityNotice
        };
    },
    components: {MarketingTaskDetails, ManualTaskList, ManualAccountStep, ManualTopicStep, ManualConfirmationLists}
});
</script>

<template>
<div class="vue2-component-root">
  <MarketingTaskDetails v-if="marketingDetails" :details="marketingDetails" @close="marketingDetails = null" />
  <div class="page-head manual-page-head">
    <div class="manual-head-actions">
      <button v-if="mode === 'create'" class="btn" type="button" @click="mode = 'list'; error = ''">返回任务列表</button>
      <button v-else class="btn primary" type="button" :disabled="!store.databaseReady" @click="startCreate">新建人工策划</button>
    </div>
  </div>
  <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
  <div v-if="notice" class="banner success-banner" role="status">{{ notice }}</div>
  <div v-if="availabilityError && mode === 'create'" class="banner error-banner manual-availability-error" role="alert">{{ availabilityError }}</div>

  <ManualTaskList v-if="mode === 'list'" @plan-details="openTaskDetails" />

  <template v-else>
    <div ref="stepperRef" class="manual-stepper" aria-label="手动策划流程">
      <button v-for="(item, index) in workflowSteps" :key="item.number" :class="['manual-step', { active: step === item.number, done: step > item.number }]" type="button" :disabled="item.number > step || busy" :aria-current="step === item.number ? 'step' : undefined" @click="returnToStep(item.number)">
        <span>{{ step > item.number ? '✓' : index + 1 }}</span><b>{{ item.label }}</b>
      </button>
    </div>

    <Transition name="manual-step-change" mode="out-in">
    <section v-if="step === 1" key="manual-step-plan" class="card">
      <div class="card-head"><div><h2>创建策划</h2></div></div>
      <div class="card-body manual-step-body">
        <div class="manual-create-meta">
          <label class="field"><span>任务名称 <em>*</em></span><input v-model="taskName" type="text" maxlength="120" placeholder="请输入任务名称" required /></label>
          <label class="field"><span>选题类型 <em>*</em></span><select v-model="contentMode"><option value="marketing">营销</option><option value="non_marketing">非营销</option></select></label>
          <label v-if="!isMarketing" class="field"><span>投放日期 <em>*</em></span><input v-model="publishDate" type="date" required /></label>
        </div>
        <div class="footer-actions manual-step-actions"><button class="btn primary" type="button" :disabled="busy" @click="savePlanStep">下一步</button></div>
      </div>
    </section>
    <ManualAccountStep v-else-if="!isMarketing && step === 2" key="manual-step-accounts" :selection="accountSelection" :marketing="isMarketing" :publish-date="publishDate" :busy="busy" :loading="catalogLoading" :initialized="store.initialized" @save="saveAccountStep" @next="confirmAccountReview" @back="returnToStep(1)" />

    <ManualTopicStep v-else-if="step === topicStepNumber" key="manual-step-topics" :selection="topicSelection" :marketing="isMarketing" :loading="catalogLoading" :initialized="store.initialized" :review.sync="topicReview" :allocation-count.sync="allocationCount" @save="saveTopicStep" @next="confirmTopicReview" @back="returnToStep(isMarketing ? 1 : 2)" />

    <section v-else-if="step === submitStepNumber" key="manual-step-submit" class="card">
      <div class="card-head"><div><h2>确认策划</h2></div></div>
      <div class="card-body manual-step-body">
        <div class="manual-submit-summary">
          <div><span>任务名称</span><b>{{ taskName }}</b></div><div><span>选题类型</span><b>{{ isMarketing ? '营销' : '非营销' }}</b></div><div v-if="isMarketing"><span>生成内容数量</span><b class="manual-review-total">{{ allocationCount }} <small>条</small></b></div><div v-else><span>账号数</span><b class="manual-review-total">{{ selectedAccounts.length }} <small>个 · 计划 {{ targetCount }} 个</small></b></div>
        </div>
        <ManualConfirmationLists :accounts="selectedAccounts" :topics="selectedTopics" :marketing="isMarketing" />        <div class="footer-actions manual-step-actions"><button class="btn" type="button" @click="returnToStep(topicStepNumber)">上一步</button><button class="btn primary" type="button" :disabled="!canSubmit" @click="submit"><span v-if="busy" class="loading-spinner" aria-hidden="true" />{{ busy ? '正在提交…' : '提交人工策划' }}</button></div>
      </div>
    </section>
    </Transition>
  </template>


  <BodyPortal>
    <Transition name="manual-eligibility-modal">
      <div v-if="eligibilityNotice" class="manual-eligibility-mask" @click.self="closeEligibilityNotice()">
        <section class="manual-eligibility-dialog" role="alertdialog" aria-modal="true" aria-labelledby="manual-eligibility-title" aria-describedby="manual-eligibility-description">
          <span class="manual-eligibility-icon" aria-hidden="true">!</span>
          <h2 id="manual-eligibility-title">选题资格不匹配</h2>
          <p id="manual-eligibility-description">{{ eligibilityNotice }}</p>
          <div class="manual-eligibility-actions"><button class="btn" type="button" @click="closeEligibilityNotice()">知道了</button><button class="btn primary" type="button" @click="closeEligibilityNotice(true)">返回修改选择</button></div>
        </section>
      </div>
    </Transition>
  </BodyPortal>
</div>
</template>

<style scoped>
.manual-stepper{display:flex;gap:0;align-items:center;min-height:64px;padding:10px 24px;margin-bottom:20px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--neutral-50);scroll-margin-top:88px}
.manual-step{display:flex;flex:1;align-items:center;gap:8px;min-height:44px;padding:0;border:0;background:transparent;color:var(--neutral-400);font-size:14px;font-weight:500;text-align:left}
.manual-step b{font-weight:500}
.manual-step:not(:last-child)::after{content:'';flex:1;height:1px;margin:0 16px;background:var(--neutral-200)}
.manual-step>span{display:grid;place-items:center;flex:none;width:28px;height:28px;border:1px solid var(--neutral-200);border-radius:50%;background:var(--surface);color:var(--neutral-400);font-size:13px;font-variant-numeric:tabular-nums}
.manual-step.active{color:var(--neutral-900)}
.manual-step.active>span{border-color:var(--primary-600);background:var(--primary-600);color:var(--surface)}
.manual-step.done{color:var(--neutral-700)}
.manual-step.done>span{background:var(--primary-50);border-color:var(--primary-200);color:var(--primary-600)}
.manual-step:disabled{opacity:1;cursor:default}
.manual-eligibility-mask{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:20px;background:var(--mask)}
.manual-eligibility-dialog{width:min(440px,100%);padding:24px;border:1px solid var(--neutral-200);border-radius:16px;background:var(--surface);box-shadow:var(--shadow-4)}
.manual-eligibility-icon{display:grid;place-items:center;width:36px;height:36px;border-radius:50%;background:var(--danger-bg);color:var(--danger);font-size:18px;font-weight:700}
.manual-eligibility-dialog h2{margin:16px 0 8px;color:var(--neutral-900);font-size:18px;line-height:26px}
.manual-eligibility-dialog p{margin:0;color:var(--neutral-600);font-size:14px;line-height:22px}
.manual-eligibility-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:24px}
.manual-eligibility-modal-enter-active,.manual-eligibility-modal-leave-active{transition:opacity .16s ease}
.manual-eligibility-modal-enter,.manual-eligibility-modal-leave-to{opacity:0}
.topic-type-badge{display:inline-flex;align-items:center;min-height:22px;padding:1px 7px;border-radius:5px;font-size:12px;line-height:18px;white-space:nowrap}.topic-type-badge.marketing{background:var(--primary-50);color:var(--primary-600)}.topic-type-badge.non-marketing{background:var(--neutral-100);color:var(--neutral-600)}
.manual-page-head{align-items:center}.manual-head-actions{display:flex;align-items:center;gap:8px}.manual-stepper{display:flex;align-items:center;gap:0;margin:0 0 18px;padding:16px 22px;border:1px solid var(--neutral-200);border-radius:10px;background:var(--surface);scroll-margin-top:76px}.manual-step{display:flex;align-items:center;gap:9px;flex:1;color:var(--neutral-400);font-size:13px}.manual-step:not(:last-child)::after{content:'';height:1px;flex:1;margin:0 16px;background:#e5e9f0}.manual-step span{display:grid;place-items:center;width:26px;height:26px;border-radius:50%;background:var(--neutral-100);font-weight:600}.manual-step.active{color:var(--primary-600)}.manual-step.active span,.manual-step.done span{background:var(--primary-600);color:var(--surface)}.manual-step.done{color:var(--neutral-700)}.manual-create-meta{display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:18px}.manual-create-meta .field{min-width:180px}.manual-unknown-list{margin-top:5px;max-height:90px;overflow:auto;color:var(--processing);font-size:12px;line-height:1.6}.manual-step-change-enter-active,.manual-step-change-leave-active{transition:opacity .2s ease,transform .2s ease}.manual-step-change-enter{opacity:0;transform:translateY(8px)}.manual-step-change-leave-to{opacity:0;transform:translateY(-5px)}.manual-step-review{display:flex;align-items:center;gap:10px;flex:1;min-width:0;padding:10px 12px;border:1px solid var(--primary-100);border-radius:8px;background:var(--primary-50)}.manual-step-review-icon{display:grid;place-items:center;flex:none;width:24px;height:24px;border-radius:50%;background:var(--primary-50);color:var(--primary-600);font-size:14px;font-weight:700}.manual-step-review>strong{flex:1;min-width:0;color:var(--neutral-700);font-size:13px;font-weight:500;line-height:1.5}.manual-step-review>strong em{display:inline-block;margin:0 2px;color:var(--primary-600);font-size:20px;font-style:normal;font-weight:700;font-variant-numeric:tabular-nums;line-height:1;vertical-align:-1px}.manual-submit-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.manual-submit-summary>div{display:flex;flex-direction:column;gap:6px;padding:14px;border:1px solid var(--neutral-200);border-radius:8px}.manual-submit-summary span,.manual-submit-group-head h3{color:var(--neutral-400);font-size:12px}.manual-submit-groups{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}.manual-submit-group{min-width:0;padding:14px;border:1px solid var(--neutral-200);border-radius:9px;background:var(--surface)}.manual-submit-group-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}.manual-submit-group-head h3{margin:0;color:var(--neutral-700);font-size:13px}.manual-submit-group-head>span{color:var(--primary-600);font-size:12px;font-weight:600}.manual-review-total{color:var(--primary-600);font-size:22px;font-variant-numeric:tabular-nums}.manual-review-total small{font-size:12px;font-weight:500}.manual-review-items{display:flex;flex-direction:column;max-height:300px;overflow:auto;border-top:1px solid var(--neutral-200)}.manual-submit-items{height:300px;overflow-y:scroll;scrollbar-gutter:stable}.manual-submit-pagination{margin-top:10px}.manual-review-item{display:flex;flex-direction:column;gap:4px;padding:9px 2px;border-bottom:1px solid var(--neutral-100)}.manual-review-item:last-child{border-bottom:0}.manual-review-item>b{color:var(--neutral-700);font-size:13px;line-height:1.45;overflow-wrap:anywhere}.manual-review-item>small{color:var(--neutral-400);font-size:11px;line-height:1.4;overflow-wrap:anywhere}.manual-selected-count{color:var(--primary-600);font-weight:600}.manual-availability-error{display:flex;align-items:center;justify-content:space-between;gap:12px}
@media(max-width:900px){.manual-submit-groups{grid-template-columns:1fr}}
@media(max-width:580px){.manual-submit-summary{grid-template-columns:1fr}.manual-stepper{padding:12px;scroll-margin-top:124px}.manual-step{gap:5px;font-size:11px}.manual-step:not(:last-child)::after{margin:0 7px}.manual-step span{width:22px;height:22px}.manual-create-meta{align-items:stretch;flex-direction:column}.manual-create-meta .field{min-width:0}.manual-step-review{flex-wrap:wrap}.manual-step-review>strong{flex-basis:calc(100% - 36px)}.manual-step-review .btn{flex:1}}
@media(prefers-reduced-motion:reduce){.manual-step-change-enter-active,.manual-step-change-leave-active{transition:none}}
</style>

<style scoped>
.manual-head-actions{margin-left:auto}
.topic-filters-toggle{display:flex;justify-content:flex-end;margin-bottom:12px}
.manual-submit-summary{grid-template-columns:repeat(3,minmax(0,1fr))}
.manual-marketing-topic-group{grid-column:1/-1}
.manual-submit-table{overflow:auto;border:1px solid var(--neutral-200);border-radius:6px}
.manual-submit-table table{width:100%;min-width:0;table-layout:fixed}
.manual-submit-table th,.manual-submit-table td{padding:10px 8px;text-align:left;font-size:12px}
.manual-submit-table th{position:sticky;top:0;z-index:1;background:var(--neutral-50);white-space:nowrap}
.manual-submit-table :deep(.manual-submit-tooltip){width:100%;min-width:0;text-align:left;font-size:12px;color:var(--neutral-700)}
.manual-submit-truncate{display:block;min-width:0;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.manual-submit-truncate.account-name,.manual-submit-truncate.topic-title{font-weight:500;color:var(--neutral-800)}
.manual-submit-truncate.identifier{font-variant-numeric:tabular-nums;color:var(--neutral-500)}
.manual-submit-truncate.topic-outline{color:var(--neutral-600)}
</style>

<style scoped>
.manual-filter-actions{display:flex;align-self:end;justify-self:start}.filter-query-inline{align-self:end;justify-self:start}.manual-count-difference{flex:none;padding:3px 8px;border-radius:5px;background:#fff4e5;color:#b54708;font-size:12px;font-weight:600}
.manual-step-body{padding-bottom:104px}.manual-step-actions{position:fixed;z-index:35;right:0;bottom:0;left:var(--sidebar-width);display:flex;align-items:center;justify-content:flex-end;min-height:68px;margin:0;padding:12px 32px calc(12px + env(safe-area-inset-bottom));border-top:1px solid var(--neutral-200);background:color-mix(in srgb,var(--surface) 94%,transparent);box-shadow:0 -6px 20px #1018280a;backdrop-filter:blur(10px)}
@media(max-width:780px){.manual-step-actions{padding-right:24px;padding-left:24px}}
@media(max-width:580px){.manual-step-body{padding-bottom:124px}.manual-step-actions{min-height:76px;padding:10px 12px calc(10px + env(safe-area-inset-bottom))}.manual-step-actions .manual-step-review{width:100%;flex-wrap:wrap}.manual-step-actions .manual-step-review>strong{flex-basis:calc(100% - 36px)}.manual-step-actions .manual-step-review .btn{flex:1}}
</style>
