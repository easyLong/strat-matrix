<script>
import { workspaceKey, workspacePages } from "../models/workspaceTabs";
import { planningRouter } from '../compat/router';
import { bindPageActivity } from "../services/pageActivity";
import { canPlanning } from '../host/runtime';
import LoadingSkeleton from '../components/LoadingSkeleton.vue';
import TaxonomyPanel from '../components/TaxonomyPanel.vue';
import ConfigOverview from '../components/config/ConfigOverview.vue';
import ConfigHistory from '../components/config/ConfigHistory.vue';
import LifecycleRulesEditor from '../components/config/LifecycleRulesEditor.vue';
import ProductionTimingConfig from '../components/config/ProductionTimingConfig.vue';
import { productionTimingValid } from '../ui/productionTiming';
import { lifecycleRangesValid } from '../ui/lifecycleRanges';
import { configValuesEqual } from '../ui/configHistory';
import { recommendedTaxonomy, tagNames } from '../topicTaxonomy';
import { api } from '../api';
import { usePlanningStore } from '../store';
export default {
  name: 'PlanningConfigPage',
  components: {
    LoadingSkeleton,
    LifecycleRulesEditor,
    TaxonomyPanel,
    ConfigOverview,
    ConfigHistory,
    ProductionTimingConfig
  },
  data() {
    return {
      draft: null,
      busy: false,
      loading: false,
      notice: '',
      error: '',
      versions: [],
      versionDetail: null,
      removeRouteGuard: undefined,
      tagVersion: 0,
      tagItems: {
        T1: [],
        T2: [],
        T3: [],
        T4: [],
        T5: []
      },
      tagBaseline: '',
      editing: false,
      historyView: false,
      confirmation: null,
      confirmationReturnFocus: null,
      confirmationResolver: undefined,
      remoteConfigPending: false,
      configSyncTimer: undefined,
      configSyncBusy: false,
      unregisterCloseGuard: null,
      configPageActive: null
    };
  },
  inject: {
    workspace: {
      from: workspaceKey,
      default: null
    }
  },
  computed: {
    store() {
      return usePlanningStore();
    },
    router() {
      return planningRouter(this);
    },
    dirty() {
      return !configValuesEqual(this.draft, this.store.config);
    },
    confirmationPanel: {
      cache: false,
      get() {
        return this.$refs.confirmationPanel || null;
      }
    },
    confirmationSafeAction: {
      cache: false,
      get() {
        return this.$refs.confirmationSafeAction || null;
      }
    },
    planningDays() {
      return this.draft.planning_days;
    },
    scheduleDay: {
      get() {
        return this.draft.schedule_day;
      },
      set(value) {
        this.draft.schedule_day = value;
      }
    },
    scheduleTime: {
      get() {
        return this.draft.schedule_time;
      },
      set(value) {
        this.draft.schedule_time = value;
      }
    },
    hotspotRatio: {
      get() {
        return this.draft.hotspot_ratio;
      },
      set(value) {
        this.draft.hotspot_ratio = value;
      }
    },
    lifecycleRules() {
      return this.draft.lifecycle_rules;
    },
    tagDirty() {
      return Boolean(this.tagBaseline) && JSON.stringify(this.tagItems) !== this.tagBaseline;
    },
    pageDirty() {
      return this.dirty || this.tagDirty;
    },
    hasUnsavedChanges() {
      return this.editing && this.pageDirty;
    },
    marketingValid() {
      return Number.isInteger(this.draft.marketing_max) && this.draft.marketing_max >= 0 && this.planningDays.length > 0 && this.planningDays.length === new Set(this.planningDays).size && this.planningDays.every(day => Number.isInteger(day) && day >= 1 && day <= 7) && Number.isInteger(this.scheduleDay) && this.scheduleDay >= 1 && this.scheduleDay <= 7 && /^([01]\d|2[0-3]):[0-5]\d$/.test(this.scheduleTime) && Number.isInteger(this.hotspotRatio) && this.hotspotRatio >= 0 && this.hotspotRatio <= 100 && productionTimingValid(this.draft.content_production_lead_days);
    },
    strategyValid() {
      return lifecycleRangesValid(this.lifecycleRules) && Number.isInteger(this.draft.rolling_posts) && this.draft.rolling_posts >= 1 && this.draft.rolling_posts <= 100 && this.draft.stage_targets.length === 5 && this.draft.stage_targets.every(stage => Number.isInteger(stage.traffic) && Number.isInteger(stage.conversion) && stage.traffic >= 0 && stage.conversion >= 0 && stage.traffic + stage.conversion === 100) && this.lifecycleRules.length === 5 && this.lifecycleRules.slice(0, 4).every(rule => !rule.catchAll && rule.conditions.length > 0 && rule.conditions.every(condition => Number.isInteger(condition.value) && condition.value >= 0)) && this.lifecycleRules[4]?.catchAll === true && this.lifecycleRules[4]?.conditions.length === 0;
    },
    canPlanning() {
      return canPlanning;
    }
  },
  methods: {
    cloneConfig(value) {
      return {
        marketing_max: value.marketing_max,
        planning_days: [...value.planning_days],
        schedule_day: value.schedule_day,
        schedule_time: value.schedule_time,
        hotspot_ratio: value.hotspot_ratio,
        ...(value.content_production_lead_days !== undefined ? {
          content_production_lead_days: value.content_production_lead_days === null ? null : {
            ...value.content_production_lead_days
          }
        } : {}),
        rolling_posts: value.rolling_posts,
        stage_targets: value.stage_targets.map(stage => ({
          ...stage
        })),
        lifecycle_rules: value.lifecycle_rules.map(rule => ({
          ...rule,
          conditions: rule.conditions.map(condition => ({
            ...condition
          }))
        }))
      };
    },
    requestConfirmation(options) {
      if (this.confirmationResolver) this.confirmationResolver(false);
      this.confirmationReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      this.confirmation = options;
      void this.$nextTick(() => {
        this.confirmationSafeAction?.focus();
      });
      return new Promise(resolve => {
        this.confirmationResolver = resolve;
      });
    },
    closeConfirmation(confirmed) {
      const resolve = this.confirmationResolver;
      this.confirmationResolver = undefined;
      this.confirmation = null;
      resolve?.(confirmed);
      const previous = this.confirmationReturnFocus;
      void this.$nextTick(() => {
        previous?.focus({
          preventScroll: true
        });
      });
    },
    dismissConfirmation() {
      this.closeConfirmation(false);
    },
    handleConfirmationKeys(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        this.dismissConfirmation();
        return;
      }
      if (event.key !== 'Tab') return;
      const buttons = this.confirmationPanel?.querySelectorAll('button:not(:disabled)');
      if (!buttons?.length) return;
      const first = buttons[0],
        last = buttons[buttons.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    },
    movePlanningDay(event, index) {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const buttons = event.currentTarget.parentElement?.querySelectorAll('button');
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? 6 : (index + (event.key === 'ArrowRight' ? 1 : -1) + 7) % 7;
      buttons?.[next]?.focus();
    },
    displayVersionNumber(version) {
      const index = this.versions.findIndex(item => item.version === version.version);
      return index < 0 ? version.version : this.versions.length - index;
    },
    togglePlanningDay(day) {
      const days = new Set(this.planningDays);
      if (days.has(day)) {
        if (days.size === 1) return;
        days.delete(day);
      } else days.add(day);
      this.draft.planning_days = [...days].sort((a, b) => a - b);
    },
    beforeUnload(event) {
      if (!this.hasUnsavedChanges) return;
      event.preventDefault();
      event.returnValue = '当前存在未保存修改，离开后修改内容将丢失。';
    },
    syncOnFocus() {
      void this.syncSavedConfig();
    },
    syncOnVisible() {
      if (!document.hidden) void this.syncSavedConfig();
    },
    async syncSavedConfig() {
      if (!this.configPageActive.active || !this.store.databaseReady || this.loading || this.busy || this.configSyncBusy || document.hidden) return;
      this.configSyncBusy = true;
      try {
        const latest = await api.config();
        if (!this.configPageActive.active || this.loading || this.busy) return;
        const changed = latest.version !== this.store.configVersion || JSON.stringify(latest.config) !== JSON.stringify(this.store.config);
        if (!changed) {
          this.remoteConfigPending = false;
          return;
        }
        if (this.pageDirty || this.editing) {
          this.remoteConfigPending = true;
          return;
        }
        this.store.applyConfig(latest);
        this.remoteConfigPending = false;
        await this.loadVersions();
      } catch (exc) {
        this.error = exc instanceof Error ? exc.message : '同步策划配置失败';
      } finally {
        this.configSyncBusy = false;
      }
    },
    async loadVersions() {
      try {
        this.versions = await api.configVersions();
      } catch (exc) {
        this.error = exc instanceof Error ? exc.message : '读取配置历史失败';
      }
    },
    async loadConfigData() {
      if (this.hasUnsavedChanges && !(await this.requestConfirmation({
        title: '加载最新配置？',
        message: '当前有未保存的配置修改，加载最新配置后这些修改将被放弃。',
        confirmLabel: '加载最新配置',
        cancelLabel: '继续编辑',
        danger: true
      }))) return;
      this.editing = false;
      this.loading = true;
      this.error = '';
      try {
        await Promise.all([this.store.refreshConfig(), this.loadVersions(), this.loadTagTaxonomy()]);
        this.remoteConfigPending = false;
      } catch (exc) {
        this.error = exc instanceof Error ? exc.message : '读取策划配置失败';
      } finally {
        this.loading = false;
      }
    },
    async loadTagTaxonomy() {
      try {
        const loaded = await api.tagTaxonomy();
        this.tagVersion = loaded.version;
        const normalizedItems = {};
        for (const code of Object.keys(tagNames)) {
          normalizedItems[code] = loaded.items[code]?.length ? loaded.items[code].map(item => ({
            ...item
          })) : recommendedTaxonomy()[code];
          this.tagItems[code] = normalizedItems[code];
        }
        // Compare against what the page actually displays. When the server has no
        // taxonomy rows yet, prototype defaults are read-only display fallbacks,
        // not unsaved user edits.
        this.tagBaseline = JSON.stringify(normalizedItems);
        // The previous page saved disabled names only in this browser. Offer them as
        // an unsaved draft when the server has no disabled labels yet.
        if (!Object.values(loaded.items).some(items => items.some(item => !item.enabled))) {
          try {
            const legacy = JSON.parse(localStorage.getItem('strat-matrix.config-ui') ?? '{}');
            const oldDisabled = legacy.disabledTags;
            let restored = false;
            for (const code of Object.keys(tagNames)) {
              const items = this.tagItems[code];
              for (const item of items) {
                if (oldDisabled?.[code]?.includes(item.name) && items.filter(tag => tag.enabled).length > 1) {
                  item.enabled = false;
                  restored = true;
                }
              }
            }
            if (restored) this.notice = '已读取此浏览器旧的停用标签，请核对并保存到服务端';
          } catch {/* Invalid old browser settings do not affect server data. */}
        }
      } catch (exc) {
        this.error = exc instanceof Error ? exc.message : '读取标签配置失败';
      }
    },
    restore() {
      if (!this.editing) return;
      this.draft = this.cloneConfig(this.store.config);
      this.notice = '已恢复到当前保存的配置';
      this.error = '';
    },
    async saveAll() {
      if (!this.editing || !this.store.databaseReady || this.busy || !this.marketingValid || !this.strategyValid || !this.pageDirty) return;
      const editedConfig = this.cloneConfig(this.draft);
      let latestSavedConfig;
      this.busy = true;
      this.notice = '';
      this.error = '';
      try {
        if (this.dirty) latestSavedConfig = await api.saveConfig(editedConfig, this.store.configVersion);
        if (latestSavedConfig) this.store.applyConfig(latestSavedConfig);
        if (this.tagDirty) {
          const savedTags = await api.saveTagTaxonomy(this.tagItems, this.tagVersion);
          this.tagVersion = savedTags.version;
          this.tagItems = savedTags.items;
          this.tagBaseline = JSON.stringify(this.tagItems);
          localStorage.removeItem('strat-matrix.config-ui');
        }
        await this.loadVersions();
        this.draft = this.cloneConfig(this.store.config);
        this.editing = false;
        this.notice = '策划配置已保存';
      } catch (exc) {
        if (latestSavedConfig) {
          this.store.applyConfig(latestSavedConfig);
          this.draft = editedConfig;
          void this.loadVersions();
        }
        this.error = exc instanceof Error ? exc.message : '保存失败';
      } finally {
        this.busy = false;
      }
    },
    async restoreVersion(version) {
      if (this.busy || version.version === this.versions[0]?.version) return;
      const visibleVersion = this.displayVersionNumber(version);
      if (!(await this.requestConfirmation({
        title: `恢复总配置 V${visibleVersion}？`,
        message: '恢复后将以该快照创建新的总配置版本，并覆盖当前账号配置与经营策略。',
        confirmLabel: '确认恢复',
        cancelLabel: '返回查看',
        danger: true
      }))) return;
      this.busy = true;
      this.error = '';
      this.notice = '';
      try {
        await this.store.restoreConfig(version.version);
        await this.loadVersions();
        this.notice = `总配置已基于 V${visibleVersion} 创建新版本`;
      } catch (exc) {
        this.error = exc instanceof Error ? exc.message : '恢复失败';
      } finally {
        this.busy = false;
      }
    },
    startEditing() {
      if (!this.store.databaseReady || this.busy || this.loading) return;
      this.editing = true;
      this.error = '';
      this.notice = '';
    },
    async openHistory() {
      if (this.loading || this.busy || !this.store.databaseReady) return;
      this.historyView = true;
      this.versionDetail = null;
      this.error = '';
      await this.loadVersions();
    },
    closeHistory() {
      this.historyView = false;
      this.versionDetail = null;
      this.error = '';
    },
    async cancelEditing() {
      if (!this.editing) return;
      if (!(await this.requestConfirmation({
        title: '取消编辑',
        message: '当前配置修改尚未保存。取消后，本次修改内容将被放弃。',
        confirmLabel: '确认取消',
        cancelLabel: '继续编辑',
        danger: true,
        safePrimary: true
      }))) return;
      this.confirmCancelEditing();
    },
    confirmCancelEditing() {
      if (!this.editing) return;
      this.draft = this.cloneConfig(this.store.config);
      try {
        const baseline = JSON.parse(this.tagBaseline || '{}');
        for (const code of Object.keys(tagNames)) this.tagItems[code] = (baseline[code] ?? []).map(item => ({
          ...item
        }));
      } catch {/* Keep the current tag values if the baseline is unavailable. */}
      this.editing = false;
      this.remoteConfigPending = false;
      this.error = '';
      this.notice = '';
    }
  },
  created() {
    this.draft = this.cloneConfig(this.store.config);
    this.unregisterCloseGuard = this.workspace?.registerCloseGuard('/config', {
      dirty: () => this.busy || this.hasUnsavedChanges,
      confirm: async () => {
        if (this.busy) return false;
        const confirmed = await this.requestConfirmation({
          title: '关闭AI策划配置？',
          message: '当前有未保存的配置修改，关闭后这些内容将被放弃。',
          confirmLabel: '确认关闭',
          cancelLabel: '继续编辑',
          danger: true,
          safePrimary: true
        });
        if (confirmed) this.confirmCancelEditing();
        return confirmed;
      }
    });
    this.$watch(() => this.store.config, value => {
      this.draft = this.cloneConfig(value);
    }, {
      deep: true
    });
    this.$watch(() => this.store.databaseReady, ready => {
      if (ready) {
        void this.loadConfigData();
      }
    }, {
      immediate: true
    });
    this.configPageActive = bindPageActivity(this, () => {
      window.addEventListener('beforeunload', this.beforeUnload);
      window.addEventListener('focus', this.syncOnFocus);
      document.addEventListener('visibilitychange', this.syncOnVisible);
      this.configSyncTimer = window.setInterval(() => {
        void this.syncSavedConfig();
      }, 10000);
      this.removeRouteGuard = this.router.beforeEach((to, from, next) => {
        // Switching local workspace tabs caches this editor; it does not discard it.
        if (this.workspace && workspacePages.some(page => page.key === to.path)) {
          next();
          return;
        }
        if (to.fullPath === from.fullPath || !this.hasUnsavedChanges) {
          next();
          return;
        }
        void this.requestConfirmation({
          title: '离开策划配置？',
          message: '当前有未保存的配置修改，离开后这些内容将被放弃。',
          confirmLabel: '放弃修改并离开',
          cancelLabel: '继续编辑',
          danger: true,
          safePrimary: true
        }).then(confirmed => {
          if (confirmed) {
            this.confirmCancelEditing();
            next();
          } else next(false);
        }, () => next(false));
      });
    }, () => {
      window.removeEventListener('beforeunload', this.beforeUnload);
      window.removeEventListener('focus', this.syncOnFocus);
      document.removeEventListener('visibilitychange', this.syncOnVisible);
      if (this.configSyncTimer !== undefined) window.clearInterval(this.configSyncTimer);
      this.removeRouteGuard?.();
    });
  },
  beforeDestroy() {
    this.unregisterCloseGuard?.();
  }
};
</script>

<template>
<div class="vue2-component-root">
  <div v-if="editing" class="page-head config-page-head"><div class="page-actions"><button class="btn" type="button" :disabled="busy" @click="cancelEditing">返回</button></div></div>
  <div v-if="historyView" class="page-head config-page-head"><div class="page-actions"><button class="btn" type="button" @click="closeHistory">返回配置</button></div></div>
  <div v-if="editing" class="config-edit-actions"><button class="btn primary" type="button" :disabled="busy || !store.databaseReady || !marketingValid || !strategyValid || !pageDirty" @click="saveAll"><span v-if="busy" class="loading-spinner" aria-hidden="true" />{{ busy ? '保存中…' : '保存配置' }}</button></div>

  <div v-if="notice" class="banner success-banner" role="status">{{ notice }}</div>
  <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
  <div v-if="remoteConfigPending" class="banner warning-banner" role="status">配置已在其它位置更新，当前编辑内容已保留。</div>

  <section v-if="loading || !store.initialized" class="card"><LoadingSkeleton :rows="8" /></section>
  <template v-if="editing && !loading && store.initialized">
  <fieldset class="form-fieldset config-stack" :disabled="!store.databaseReady || busy || loading">
    <section class="card">
      <div class="card-head"><div><h2>策划内容配置</h2></div></div>
      <div class="card-body">
        <div class="form-grid config-control-grid">
          <div class="field"><span>每周策划日</span><div class="day-picker"><button v-for="day in [{ n: 1, label: '周一' }, { n: 2, label: '周二' }, { n: 3, label: '周三' }, { n: 4, label: '周四' }, { n: 5, label: '周五' }, { n: 6, label: '周六' }, { n: 7, label: '周日' }]" :key="day.n" class="day-chip" :class="{ active: planningDays.includes(day.n) }" type="button" :aria-pressed="planningDays.includes(day.n)" @keydown="movePlanningDay($event, day.n - 1)" @click="togglePlanningDay(day.n)">{{ day.label }}</button></div></div>
          <label class="field"><span>自动策划调度时间</span><div class="schedule-picker"><select v-model.number="scheduleDay"><option :value="1">周一</option><option :value="2">周二</option><option :value="3">周三</option><option :value="4">周四</option><option :value="5">周五</option><option :value="6">周六</option><option :value="7">周日</option></select><input v-model="scheduleTime" type="time" /></div></label>
          <label class="field"><span>营销内容周上限</span><div class="input-unit"><input v-model.number="draft.marketing_max" type="number" min="0" /><span>条 / 营销账号 / 周</span></div></label>
          <label class="field"><span>热点选题占比</span><div class="input-unit"><input v-model.number="hotspotRatio" type="number" min="0" max="100" /><span>%</span></div></label>
        </div>

        <ProductionTimingConfig v-model="draft.content_production_lead_days" />
        <p v-if="editing && !marketingValid" class="inline-error">请检查策划日、调度时间、营销上限、热点占比，以及0至365之间的内容生产提前天数。</p>

      </div>
    </section>

    <section class="card">
      <div class="card-head config-rules-head"><h2>策划规则配置</h2><label class="config-window-inline"><span>滚动统计窗口</span><div class="input-unit"><input v-model.number="draft.rolling_posts" aria-label="滚动统计窗口" type="number" min="1" max="100" /><span>篇</span></div></label></div>
      <div class="card-body">
        <LifecycleRulesEditor v-model="draft.lifecycle_rules" />
        <div class="lifecycle-definition-head"><div><b>阶段经营目标</b></div></div>
        <div class="stage-table-wrap">
          <table class="stage-table"><thead><tr><th>生命周期阶段</th><th>流量目标</th><th>转化目标</th><th>合计</th></tr></thead>
            <tbody><tr v-for="stage in draft.stage_targets" :key="stage.name">
              <td><b>{{ stage.name }}</b></td>
              <td><div class="input-unit compact"><input v-model.number="stage.traffic" type="number" min="0" max="100" /><span>%</span></div></td>
              <td><div class="input-unit compact"><input v-model.number="stage.conversion" type="number" min="0" max="100" /><span>%</span></div></td>
              <td><span :class="['tag', stage.traffic + stage.conversion === 100 ? 'green' : 'red']">{{ stage.traffic + stage.conversion }}%</span></td>
            </tr></tbody>
          </table>
        </div>

        <div class="lifecycle-definition-head"><div><b>选题标签配置</b></div></div>
        <TaxonomyPanel :model-value.sync="tagItems" :editing="editing" :disabled="busy || !store.databaseReady" />
        <p v-if="editing && !strategyValid" class="inline-error">请检查滚动窗口、生命周期条件范围；每个阶段的流量与转化目标之和必须为 100%。</p>
      </div>
    </section>
  </fieldset>
  </template>
  <template v-else-if="!historyView && !loading && store.initialized">
  <ConfigOverview :config="draft" :tag-items="tagItems"><template #actions><button v-if="canPlanning('config.edit')" class="btn primary" type="button" :disabled="loading || busy || !store.databaseReady" @click="startEditing">编辑配置</button><button class="btn" type="button" :disabled="loading || busy || !store.databaseReady" @click="openHistory">历史配置</button></template></ConfigOverview>
  </template>
  <ConfigHistory v-if="historyView && !loading && store.initialized" :detail.sync="versionDetail" :versions="versions" :disabled="busy" @restore="restoreVersion" />
  <div v-if="confirmation" class="app-confirm-mask" @click.self="dismissConfirmation">
    <section ref="confirmationPanel" class="app-confirm" role="alertdialog" aria-modal="true" aria-labelledby="app-confirm-title" aria-describedby="app-confirm-description" @keydown.stop="handleConfirmationKeys">
      <div class="app-confirm-icon" :class="{ danger: confirmation.danger }" aria-hidden="true">{{ confirmation.danger ? '!' : 'i' }}</div>
      <h2 id="app-confirm-title">{{ confirmation.title }}</h2>
      <p id="app-confirm-description">{{ confirmation.message }}</p>
      <div class="app-confirm-actions">
        <template v-if="confirmation.danger && confirmation.safePrimary">
          <button class="btn" type="button" @click="closeConfirmation(true)">{{ confirmation.confirmLabel }}</button>
          <button ref="confirmationSafeAction" class="btn app-confirm-danger" type="button" @click="closeConfirmation(false)">{{ confirmation.cancelLabel }}</button>
        </template>
        <template v-else-if="confirmation.danger">
          <button ref="confirmationSafeAction" class="btn" type="button" @click="closeConfirmation(false)">{{ confirmation.cancelLabel }}</button>
          <button class="btn app-confirm-danger" type="button" @click="closeConfirmation(true)">{{ confirmation.confirmLabel }}</button>
        </template>
        <button v-else class="btn primary" type="button" @click="closeConfirmation(true)">{{ confirmation.confirmLabel }}</button>
      </div>
    </section>
  </div>
</div>
</template>

<style scoped>
.config-stack{gap:20px;margin-bottom:20px}
.config-stack>.card{margin-bottom:0}
.config-stack .card-head{padding:16px 24px}
.config-stack .card-head h2{font-size:16px;line-height:24px;font-weight:600}
.config-stack .card-body{padding:16px 24px}
.config-stack .config-control-grid{gap:12px 28px}
.config-stack .field{gap:8px;font-size:13px;font-weight:400}
.config-stack .day-picker{gap:5px}
.config-stack .day-chip{position:relative;height:32px;padding:0 11px;border-radius:999px;font-size:13px;font-weight:500}
.config-stack .day-chip::after{content:'';position:absolute;inset:-6px 0}
.config-stack .day-chip.active::before{content:'✓';margin-right:5px}
.config-stack .schedule-picker{width:280px;max-width:100%;gap:6px}
.config-stack .schedule-picker select,.config-stack .schedule-picker input{height:32px;min-height:32px;font-size:12px}
.config-stack .schedule-picker input{width:116px}
.config-stack .input-unit{height:32px}
.config-stack .input-unit input{width:64px;height:32px;min-height:32px;padding:0 8px;font-size:13px}
.config-stack .input-unit span{font-size:11px;padding-right:8px}
.config-stack .rolling-field{flex-direction:row;align-items:center;gap:10px;margin-bottom:10px}
.config-stack .stage-table-wrap{border:1px solid var(--neutral-200);border-radius:7px}
.config-stack .stage-table{min-width:460px}
.config-stack .stage-table th,.config-stack .stage-table td{height:44px;padding:6px 12px;font-size:13px;font-variant-numeric:tabular-nums}
.config-stack .stage-table .tag{margin-left:0;padding:2px 7px;font-size:11px}
.config-stack .lifecycle-stage-name{padding:0}
.config-stack .lifecycle-stage-name b{font-size:14px;line-height:22px;font-weight:600}
.config-stack .condition-unit{grid-column:4;font-size:11px}
.config-stack .condition-join{grid-column:5;width:44px!important}
.config-stack .condition-remove{grid-column:6;width:22px;height:26px;font-size:18px!important}
.config-stack .condition-remove:hover{color:var(--danger);background:var(--danger-bg);border-radius:5px}
.config-stack .condition-add{justify-self:start;padding:2px 0;font-size:11px}
.config-stack .lifecycle-catch-all{font-size:12px;line-height:1.6;color:var(--neutral-500)}
@media(max-width:780px){.config-stack .config-control-grid{grid-template-columns:minmax(0,1fr);gap:12px}.config-stack .card-body{padding:12px}}
@media(max-width:580px){.config-stack .condition-unit{grid-column:3;grid-row:2}.config-stack .condition-join{grid-column:4;grid-row:2}.config-stack .condition-remove{grid-column:5;grid-row:2}}
.tag-content-title{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.tag-tabs-with-hint{display:flex;align-items:center;flex-wrap:wrap;gap:0 20px;padding:0 24px;border-bottom:1px solid var(--neutral-200)}
.tag-tabs-with-hint .tag-tabs{min-width:0;max-width:100%;padding:0;border-bottom:0}
.tag-user-need-hint{min-height:44px;font-weight:500}
.tag-content-head{align-items:center;justify-content:flex-start;flex-wrap:wrap;gap:14px;min-height:34px}
.tag-context-popover{position:fixed;z-index:70;box-sizing:border-box;width:132px;max-width:calc(100vw - 16px);padding:5px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface);box-shadow:var(--shadow-3)}
.tag-context-popover.is-renaming{width:264px;padding:12px}
.tag-menu-item{display:flex;align-items:center;gap:9px;width:100%;height:32px;padding:0 9px;border:0;border-radius:5px;background:transparent;color:var(--neutral-600);font:inherit;font-size:12px;text-align:left;cursor:pointer}
.tag-menu-item:hover,.tag-menu-item:focus-visible{outline:none;background:var(--primary-50);color:var(--primary-600)}
.tag-menu-item.is-danger{color:var(--danger)}
.tag-menu-item.is-danger:hover,.tag-menu-item.is-danger:focus-visible{background:var(--danger-bg);color:var(--danger-hover)}
.tag-menu-item:disabled{opacity:.6;cursor:default}
.tag-menu-error{display:block;margin:7px 6px 4px;color:var(--danger);font-size:11px;line-height:1.5}
.tag-selection-actions{display:flex;align-items:center;justify-content:flex-end;gap:14px;margin-top:10px}
.tag-rename-input{box-sizing:border-box;width:100%;min-width:0;height:32px;padding:0 9px;border:1px solid var(--neutral-200);border-radius:6px;color:var(--neutral-900);background:var(--surface);font:inherit;font-size:12px}
.tag-rename-input:focus{outline:2px solid var(--focus-color);border-color:var(--primary-600)}
.tag-action-muted{color:var(--neutral-400)}
.tag-pills{--label-color:var(--primary-600);--label-background:var(--primary-50);--label-border:var(--primary-100)}
.tag-content .tag-pills{align-items:flex-start;gap:6px;min-height:0;padding:2px 0}
.tag-pills>.pill-edit{display:inline-flex;align-items:center;justify-content:center;min-width:0;min-height:26px;max-width:100%;padding:3px 9px;border:1px solid var(--label-border);border-radius:5px;background:var(--label-background);color:var(--label-color);font-family:inherit;font-size:12px;font-weight:500;line-height:18px;overflow-wrap:anywhere;text-align:left;cursor:pointer;transition:border-color .15s,box-shadow .15s}
.tag-pills>.pill-edit:not(:disabled):hover{border-color:var(--label-color)}
.tag-pills>.pill-edit.disabled{border-style:dashed;border-color:var(--neutral-200);background:var(--neutral-50);color:var(--neutral-400);text-decoration:none}
.tag-pills>.pill-edit.selected{border-color:var(--label-color);box-shadow:0 0 0 1px var(--label-color)}
.tag-pills>.pill-edit:focus-visible{outline:2px solid var(--primary-600);outline-offset:2px}
.tag-pills>.pill-edit:disabled{cursor:default;opacity:.6}
.app-confirm-mask{position:fixed;inset:0;z-index:80;display:grid;place-items:center;padding:20px;background:var(--mask)}
.app-confirm{width:min(400px,100%);padding:26px 28px 22px;border:1px solid #e7ebf2;border-radius:16px;background:var(--surface);box-shadow:var(--shadow-4);text-align:left;animation:app-confirm-in .16s ease-out}
.app-confirm-icon{display:grid;place-items:center;width:42px;height:42px;margin:0 0 16px;border:1px solid var(--primary-100);border-radius:50%;background:#f2f7ff;color:var(--primary-600);font-size:21px;font-weight:750}
.app-confirm-icon.danger{border-color:var(--processing-bg);background:var(--processing-bg);color:var(--processing);font-size:23px}
.app-confirm h2{margin:0;color:var(--neutral-900);font-size:18px;line-height:1.4}
.app-confirm p{margin:9px 0 24px;color:var(--neutral-500);font-size:13px;line-height:1.7}
.app-confirm-actions{display:flex;justify-content:flex-end;gap:8px}
.app-confirm-actions .btn{min-width:112px}
.app-confirm-danger{border-color:var(--danger);background:var(--danger);color:var(--surface)}
.app-confirm-danger:hover{border-color:var(--danger-hover);background:var(--danger-hover)}
@keyframes app-confirm-in{from{opacity:0;transform:translateY(5px) scale(.985)}to{opacity:1;transform:translateY(0) scale(1)}}
</style>


<style scoped>
.config-page-head .page-actions{margin-left:auto}
</style>
