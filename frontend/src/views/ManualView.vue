<script>
import { planningRouter } from '../compat/router';
import { canPlanning } from '../host/runtime';
import { bindPageActivity } from "../services/pageActivity";
import ManualAccountStep from '../components/manual/ManualAccountStep.vue';
import { createAccountSelection } from "../models/accountSelection";
import ManualTopicStep from '../components/manual/ManualTopicStep.vue';
import { createTopicSelection } from "../models/topicSelection";
import ManualTaskList from '../components/manual/ManualTaskList.vue';
import MarketingTaskDetails from '../components/MarketingTaskDetails.vue';
import { api } from '../api';
import ManualConfirmationLists from '../components/ManualConfirmationLists.vue';
import { usePlanningStore } from '../store';
import { createRequestId } from '../ui/requestId';
import { beijingDate } from '../ui/manualTopics';
export default {
  name: 'PlanningManualPage',
  components: {
    MarketingTaskDetails,
    ManualTaskList,
    ManualAccountStep,
    ManualTopicStep,
    ManualConfirmationLists
  },
  data() {
    return {
      step: 1,
      busy: false,
      taskName: '',
      contentMode: 'non_marketing',
      allocationCount: '',
      marketingRequestId: '',
      marketingDetails: null,
      publishDate: '',
      today: beijingDate(),
      validityTimer: undefined,
      accounts: [],
      topics: [],
      catalogLoading: false,
      catalogRequest: 0,
      error: '',
      notice: '',
      accountSelection: null,
      eligibilityNotice: '',
      topicReview: false,
      topicSelection: null
    };
  },
  computed: {
    store() {
      return usePlanningStore();
    },
    router() {
      return planningRouter(this);
    },
    mode: {
      get() {
        return this.store.manualCreating ? 'create' : 'list';
      },
      set(value) {
        this.store.manualCreating = value === 'create';
      }
    },
    stepperRef: {
      cache: false,
      get() {
        return this.$refs.stepperRef || null;
      }
    },
    isMarketing() {
      return this.contentMode === 'marketing';
    },
    workflowSteps() {
      return this.isMarketing ? [{
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
      }];
    },
    topicStepNumber() {
      return this.isMarketing ? 2 : 3;
    },
    submitStepNumber() {
      return this.isMarketing ? 3 : 4;
    },
    validAllocationCount() {
      return Number.isInteger(this.allocationCount) && Number(this.allocationCount) >= 1 && Number(this.allocationCount) <= 1000;
    },
    sampledIds: {
      get() {
        return this.accountSelection.sampledIds;
      },
      set(value) {
        this.accountSelection.sampledIds = value;
      }
    },
    selectedAccounts: {
      get() {
        return this.accountSelection.selectedAccounts;
      },
      set(value) {
        this.accountSelection.selectedAccounts = value;
      }
    },
    targetCount: {
      get() {
        return this.accountSelection.targetCount;
      },
      set(value) {
        this.accountSelection.targetCount = value;
      }
    },
    accountReview: {
      get() {
        return this.accountSelection.accountReview;
      },
      set(value) {
        this.accountSelection.accountReview = value;
      }
    },
    availabilityReady: {
      get() {
        return this.accountSelection.availabilityReady;
      },
      set(value) {
        this.accountSelection.availabilityReady = value;
      }
    },
    availabilityError: {
      get() {
        return this.accountSelection.availabilityError;
      },
      set(value) {
        this.accountSelection.availabilityError = value;
      }
    },
    loadAccountAvailability: {
      get() {
        return this.accountSelection.loadAccountAvailability;
      },
      set(value) {
        this.accountSelection.loadAccountAvailability = value;
      }
    },
    accountSelectionMode: {
      get() {
        return this.accountSelection.accountSelectionMode;
      },
      set(value) {
        this.accountSelection.accountSelectionMode = value;
      }
    },
    importDataRowCount: {
      get() {
        return this.accountSelection.importDataRowCount;
      },
      set(value) {
        this.accountSelection.importDataRowCount = value;
      }
    },
    accountPage: {
      get() {
        return this.accountSelection.accountPage;
      },
      set(value) {
        this.accountSelection.accountPage = value;
      }
    },
    accountListRef: {
      get() {
        return this.accountSelection.accountListRef;
      },
      set(value) {
        this.accountSelection.accountListRef = value;
      }
    },
    selectedTopicIds: {
      get() {
        return this.topicSelection.selectedTopicIds;
      },
      set(value) {
        this.topicSelection.selectedTopicIds = value;
      }
    },
    selectedTopics: {
      get() {
        return this.topicSelection.selectedTopics;
      },
      set(value) {
        this.topicSelection.selectedTopics = value;
      }
    },
    topicPage: {
      get() {
        return this.topicSelection.topicPage;
      },
      set(value) {
        this.topicSelection.topicPage = value;
      }
    },
    topicListRef: {
      get() {
        return this.topicSelection.topicListRef;
      },
      set(value) {
        this.topicSelection.topicListRef = value;
      }
    },
    canSubmit() {
      return this.topicSelection.selectionValid && (this.isMarketing ? this.store.databaseReady && !this.busy && this.taskName.trim() !== '' && this.selectedTopicIds.length === 1 && this.validAllocationCount : this.store.databaseReady && this.availabilityReady && !this.busy && this.taskName.trim() !== '' && this.sampledIds.length > 0 && this.selectedTopicIds.length > 0 && this.publishDate !== '');
    },
    canPlanning() {
      return canPlanning;
    }
  },
  methods: {
    async revealStepProgress() {
      await this.$nextTick();
      const stepper = this.stepperRef;
      stepper?.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
      const activeStep = stepper?.querySelector('.manual-step.active');
      if (stepper && activeStep && stepper.scrollWidth > stepper.clientWidth) {
        stepper.scrollTo({
          left: Math.max(0, activeStep.offsetLeft - stepper.offsetLeft - 16),
          behavior: 'smooth'
        });
      }
    },
    async resetSelectionListScroll(target) {
      await this.$nextTick();
      const list = target === 'accounts' ? this.accountListRef : this.topicListRef;
      if (list) {
        list.scrollTop = 0;
        list.scrollLeft = 0;
      }
    },
    async loadCatalog() {
      const request = ++this.catalogRequest;
      this.catalogLoading = true;
      try {
        const [accountRows, topicRows] = await Promise.all([api.accounts(), api.topics()]);
        if (request !== this.catalogRequest) return;
        this.accounts = accountRows;
        this.topics = topicRows;
      } catch (exc) {
        if (request === this.catalogRequest) this.error = exc instanceof Error ? exc.message : '读取账号和选题失败';
      } finally {
        if (request === this.catalogRequest) this.catalogLoading = false;
      }
    },
    async openTaskDetails(task) {
      // 已生成正式批次的任务统一复用策划结果中的批次策划详情。
      if (task.batch_id) {
        void this.router.push({
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
          this.marketingDetails = await api.marketingTaskDetails(task.task_code);
        } catch (exc) {
          this.error = exc instanceof Error ? exc.message : '读取营销策划失败';
        }
        return;
      }
      if (!task.batch_id) return;
      void this.router.push({
        path: '/results',
        query: {
          batch: String(task.batch_id),
          plan_type: 'manual',
          from: 'manual'
        }
      });
    },
    startCreate() {
      this.contentMode = 'non_marketing';
      this.allocationCount = '';
      this.marketingRequestId = createRequestId();
      this.publishDate = '';
      this.step = 1;
      this.taskName = '';
      this.accountSelection.reset();
      this.topicSelection.reset();
      this.accountReview = false;
      this.topicReview = false;
      this.error = '';
      this.notice = '';
      this.eligibilityNotice = '';
      this.mode = 'create';
    },
    returnToStep(next) {
      if (next >= this.step || this.busy) return;
      this.step = next;
      if (!this.isMarketing && next <= 2) this.accountReview = false;
      if (next <= this.topicStepNumber) this.topicReview = false;
      void this.revealStepProgress();
    },
    savePlanStep() {
      this.error = '';
      if (!this.taskName.trim()) {
        this.error = '请输入任务名称';
        return;
      }
      if (!this.isMarketing && !this.publishDate) {
        this.error = '请选择投放日期';
        return;
      }
      this.step = 2;
      void this.revealStepProgress();
    },
    async saveAccountStep() {
      this.error = '';
      if (!this.taskName.trim()) {
        this.error = '请输入任务名称';
        return;
      }
      if (!this.isMarketing && !this.publishDate) {
        this.error = '请选择投放日期';
        return;
      }
      if (this.accountSelectionMode === 'filter') {
        if (this.targetCount === '') {
          this.error = '请输入计划账号数量';
          return;
        }
        if (!Number.isInteger(this.targetCount) || this.targetCount < 1 || this.targetCount > 1000) {
          this.error = '计划账号数量须为 1 至 1000 之间的整数';
          return;
        }
      } else if (this.accountSelectionMode === 'upload') {
        if (!this.importDataRowCount) {
          this.error = '请先导入账号模板';
          return;
        }
        this.targetCount = this.importDataRowCount;
      }
      if (!this.sampledIds.length) {
        this.error = '请先选择账号';
        return;
      }
      if (!(await this.loadAccountAvailability())) return;
      if (!this.sampledIds.length) {
        this.error = '所选账号当日已手动策划，请重新选择';
        return;
      }
      this.accountPage = 1;
      this.accountReview = true;
      void this.resetSelectionListScroll('accounts');
    },
    saveTopicStep() {
      this.error = '';
      if (!this.topicSelection.validateSelection()) return;
      if (!this.selectedTopicIds.length || this.isMarketing && this.selectedTopicIds.length !== 1) {
        this.error = this.isMarketing ? '请选择一个选题' : '请至少选择一个选题';
        return;
      }
      if (this.isMarketing && !this.validAllocationCount) {
        this.error = '请输入 1 至 1000 之间的生成内容数量';
        return;
      }
      this.topicPage = 1;
      this.topicReview = true;
      void this.resetSelectionListScroll('topics');
    },
    confirmAccountReview() {
      if (!this.availabilityReady || !this.sampledIds.length) {
        this.accountReview = false;
        this.error = '请重新确认可策划账号后再继续';
        return;
      }
      this.accountReview = true;
      this.step = 3;
      void this.revealStepProgress();
    },
    confirmTopicReview() {
      if (!this.topicSelection.validateSelection()) return;
      if (!this.selectedTopicIds.length || this.isMarketing && this.selectedTopicIds.length !== 1) {
        this.topicReview = false;
        this.error = this.isMarketing ? '请选择一个选题' : '请选择至少一个选题';
        return;
      }
      if (this.isMarketing && !this.validAllocationCount) {
        this.topicReview = false;
        this.error = '请输入 1 至 1000 之间的生成内容数量';
        return;
      }
      this.topicReview = true;
      this.step = this.submitStepNumber;
      this.error = '';
      void this.revealStepProgress();
    },
    async submit() {
      if (!this.topicSelection.validateSelection()) return;
      if (!this.canSubmit) return;
      this.busy = true;
      this.error = '';
      this.notice = '';
      this.eligibilityNotice = '';
      try {
        if (this.isMarketing) {
          await api.createMarketingTask({
            request_id: this.marketingRequestId,
            task_name: this.taskName.trim(),
            topic_id: this.selectedTopicIds[0],
            allocation_count: Number(this.allocationCount)
          });
          this.mode = 'list';
          this.notice = '营销策划已提交';
          return;
        }
        const selectedCount = this.sampledIds.length;
        if (!(await this.loadAccountAvailability())) return;
        if (this.sampledIds.length !== selectedCount) {
          this.step = 2;
          this.error = '部分账号当日已手动策划，已移除，请重新确认账号数量';
          return;
        }
        const preview = await api.previewManual({
          content_mode: 'non_marketing',
          task_name: this.taskName.trim(),
          publish_date: this.publishDate,
          account_ids: this.sampledIds,
          target_count: selectedCount,
          topic_ids: this.selectedTopicIds,
          note: ''
        });
        await api.submitManualPreview(preview.preview_id);
        this.notice = '手动策划已提交，当前状态：生成中';
        this.mode = 'list';
      } catch (exc) {
        this.error = exc instanceof Error ? exc.message : '提交手动策划失败';
        if (this.error.includes('不具备所选营销选题资格')) this.eligibilityNotice = this.error;
      } finally {
        this.busy = false;
      }
    },
    closeEligibilityNotice(returnToSelection = false) {
      this.eligibilityNotice = '';
      if (returnToSelection) {
        this.error = '';
        this.accountReview = false;
        this.topicReview = false;
        this.step = 1;
        void this.revealStepProgress();
      }
    },
    fetchAvailability(date) {
      return api.manualAccountAvailability(date);
    }
  },
  created() {
    bindPageActivity(this, () => {
      this.today = beijingDate();
      this.validityTimer = setInterval(() => {
        this.today = beijingDate();
      }, 30000);
    }, () => {
      if (this.validityTimer !== undefined) clearInterval(this.validityTimer);
    });
    this.$watch(() => [this.taskName, this.allocationCount], () => {
      this.marketingRequestId = createRequestId();
    }, {
      sync: true
    });
    this.$watch(() => this.allocationCount, () => {
      if (this.validAllocationCount && this.error === '请输入 1 至 1000 之间的生成内容数量') this.error = '';
    });
    this.accountSelection = createAccountSelection(this);
    this.topicSelection = createTopicSelection(this);
    this.$watch(() => this.selectedTopicIds, () => {
      this.marketingRequestId = createRequestId();
    }, {
      sync: true
    });
    this.$watch(() => this.contentMode, () => {
      this.accountSelection.reset();
      this.topicSelection.reset();
      this.topicReview = false;
      this.marketingRequestId = createRequestId();
    });
    this.$watch(() => [this.store.databaseReady, this.mode], ([ready, current]) => {
      if (ready && current === 'create') void this.loadCatalog();else {
        this.catalogRequest++;
        this.catalogLoading = false;
      }
    }, {
      immediate: true
    });
  },
  beforeDestroy() {
    this.accountSelection?.$destroy();
    this.topicSelection?.$destroy();
    this.catalogRequest++;
    this.store.manualCreating = false;
  }
};
</script>

<template>
<div class="vue2-component-root">
  <MarketingTaskDetails v-if="marketingDetails" :details="marketingDetails" @close="marketingDetails = null" />
  <div v-if="mode !== 'create'" class="page-head manual-page-head">
    <div class="manual-head-actions">

      <button v-if="canPlanning('manual.create')" class="btn primary" type="button" :disabled="!store.databaseReady" @click="startCreate">新建人工策划</button>
    </div>
  </div>
  <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
  <div v-if="notice" class="banner success-banner" role="status">{{ notice }}</div>
  <div v-if="availabilityError && mode === 'create'" class="banner error-banner manual-availability-error" role="alert">{{ availabilityError }}</div>

  <ManualTaskList v-if="mode === 'list'" @plan-details="openTaskDetails" />

  <template v-else>
    <div class="manual-create-toolbar"><button class="text-btn manual-back" type="button" aria-label="返回" @click="mode='list'; error=''">← 返回</button><span class="manual-task-context">{{ taskName || '新建人工策划' }}</span></div><div ref="stepperRef" class="manual-stepper" aria-label="手动策划流程">
      <button v-for="(item, index) in workflowSteps" :key="item.number" :class="['manual-step', { active: step === item.number, done: step > item.number }]" type="button" :disabled="item.number > step || busy" :aria-current="step === item.number ? 'step' : undefined" @click="returnToStep(item.number)">
        <span>{{ step > item.number ? '✓' : index + 1 }}</span><b>{{ item.label }}</b>
      </button>
    </div>

    <Transition name="manual-step-change" mode="out-in">
    <section v-if="step === 1" key="manual-step-plan" class="card">
      <div class="card-head"><div><h2>创建策划</h2></div></div>
      <div class="card-body manual-step-body">
        <div class="manual-create-meta">
          <label class="field"><span>任务名称 <em class="required-mark">✳</em></span><input v-model="taskName" type="text" maxlength="120" placeholder="请输入任务名称" required /></label>
          <label class="field"><span>选题类型 <em class="required-mark">✳</em></span><select v-model="contentMode"><option value="marketing">营销</option><option value="non_marketing">非营销</option></select></label>
          <label v-if="!isMarketing" class="field"><span>投放日期 <em class="required-mark">✳</em></span><input v-model="publishDate" type="date" required /></label>
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
.manual-page-head{align-items:center}.manual-head-actions{display:flex;align-items:center;gap:8px}.manual-stepper{display:flex;align-items:center;gap:0;margin:0 0 18px;padding:16px 22px;border:1px solid var(--neutral-200);border-radius:10px;background:var(--surface);scroll-margin-top:76px}.manual-step{display:flex;align-items:center;gap:9px;flex:1;color:var(--neutral-400);font-size:13px}.manual-step:not(:last-child)::after{content:'';height:1px;flex:1;margin:0 16px;background:#e5e9f0}.manual-step span{display:grid;place-items:center;width:26px;height:26px;border-radius:50%;background:var(--neutral-100);font-weight:600}.manual-step.active{color:var(--primary-600)}.manual-step.active span,.manual-step.done span{background:var(--primary-600);color:var(--surface)}.manual-step.done{color:var(--neutral-700)}.manual-create-meta{display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:18px}.manual-create-meta .field{min-width:180px}.manual-unknown-list{margin-top:5px;max-height:90px;overflow:auto;color:var(--processing);font-size:12px;line-height:1.6}.manual-step-change-enter-active,.manual-step-change-leave-active{transition:opacity .16s ease}.manual-step-change-enter{opacity:0}.manual-step-change-leave-to{opacity:0}.manual-step-review{display:flex;align-items:center;gap:10px;flex:1;min-width:0;padding:10px 12px;border:1px solid var(--primary-100);border-radius:8px;background:var(--primary-50)}.manual-step-review-icon{display:grid;place-items:center;flex:none;width:24px;height:24px;border-radius:50%;background:var(--primary-50);color:var(--primary-600);font-size:14px;font-weight:700}.manual-step-review>strong{flex:1;min-width:0;color:var(--neutral-700);font-size:13px;font-weight:500;line-height:1.5}.manual-step-review>strong em{display:inline-block;margin:0 2px;color:var(--primary-600);font-size:20px;font-style:normal;font-weight:700;font-variant-numeric:tabular-nums;line-height:1;vertical-align:-1px}.manual-submit-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.manual-submit-summary>div{display:flex;flex-direction:column;gap:6px;padding:14px;border:1px solid var(--neutral-200);border-radius:8px}.manual-submit-summary span,.manual-submit-group-head h3{color:var(--neutral-400);font-size:12px}.manual-submit-groups{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}.manual-submit-group{min-width:0;padding:14px;border:1px solid var(--neutral-200);border-radius:9px;background:var(--surface)}.manual-submit-group-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}.manual-submit-group-head h3{margin:0;color:var(--neutral-700);font-size:13px}.manual-submit-group-head>span{color:var(--primary-600);font-size:12px;font-weight:600}.manual-review-total{color:var(--primary-600);font-size:22px;font-variant-numeric:tabular-nums}.manual-review-total small{font-size:12px;font-weight:500}.manual-review-items{display:flex;flex-direction:column;max-height:300px;overflow:auto;border-top:1px solid var(--neutral-200)}.manual-submit-items{height:300px;overflow-y:scroll;scrollbar-gutter:stable}.manual-submit-pagination{margin-top:10px}.manual-review-item{display:flex;flex-direction:column;gap:4px;padding:9px 2px;border-bottom:1px solid var(--neutral-100)}.manual-review-item:last-child{border-bottom:0}.manual-review-item>b{color:var(--neutral-700);font-size:13px;line-height:1.45;overflow-wrap:anywhere}.manual-review-item>small{color:var(--neutral-400);font-size:11px;line-height:1.4;overflow-wrap:anywhere}.manual-selected-count{color:var(--primary-600);font-weight:600}.manual-availability-error{display:flex;align-items:center;justify-content:space-between;gap:12px}
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
.manual-submit-table ::v-deep .manual-submit-tooltip{width:100%;min-width:0;text-align:left;font-size:12px;color:var(--neutral-700)}
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
