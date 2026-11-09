<script>
import { RouterLink, RouterView, planningRoute } from './compat/router';
import { api } from './api';
import { usePlanningStore } from './store';
import WorkspaceTabs from './components/WorkspaceTabs.vue';
import { createWorkspaceTabs, workspaceKey } from "./models/workspaceTabs";
import { bindPageActivity } from "./services/pageActivity";
import { canPlanning } from './host/runtime';
export default {
  props: {
    embedded: {
      type: Boolean,
      default: false
    }
  },
  components: {
    RouterLink,
    WorkspaceTabs,
    RouterView
  },
  data() {
    return {
      workspace: null,
      resultsUiObserver: undefined,
      profileRequest: undefined,
      profileAttempted: false,
      accountProfiles: new Map(),
      nav: [{
        to: '/config',
        icon: 'M4 6h16M4 12h16M4 18h16M9 3v6m6 0v6m-7 0v6',
        label: 'AI策划配置'
      }, {
        to: '/manual',
        icon: 'm15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15z',
        label: '人工策划'
      }, {
        to: '/results',
        icon: 'M4 4h16v16H4zM9 4v16M4 10h16M13 14h3m-3 3h3',
        label: '策划结果'
      }]
    };
  },
  computed: {
    store() {
      return usePlanningStore();
    },
    appRoot: {
      cache: false,
      get() {
        return this.$refs.appRoot || null;
      }
    },
    route() {
      return planningRoute(this);
    },
    activeNav() {
      return this.route.path;
    },
    canPlanning() {
      return canPlanning;
    },
    workspaceTabs: {
      get() {
        return this.workspace.tabs;
      },
      set(value) {
        this.workspace.tabs = value;
      }
    },
    workspaceClosing: {
      get() {
        return this.workspace.closing;
      },
      set(value) {
        this.workspace.closing = value;
      }
    },
    workspaceCacheNames: {
      get() {
        return this.workspace.cacheNames;
      },
      set(value) {
        this.workspace.cacheNames = value;
      }
    },
    selectWorkspace: {
      get() {
        return this.workspace.select;
      },
      set(value) {
        this.workspace.select = value;
      }
    },
    closeWorkspace: {
      get() {
        return this.workspace.close;
      },
      set(value) {
        this.workspace.close = value;
      }
    },
    workspaceLocation: {
      get() {
        return this.workspace.locationFor;
      },
      set(value) {
        this.workspace.locationFor = value;
      }
    }
  },
  methods: {
    withinApp(selector) {
      return this.appRoot?.querySelectorAll(selector) || [];
    },
    compactPlanningSourceBadges() {
      this.withinApp('.account-week-plan-tags .tag.gray').forEach(badge => {
        const label = badge.textContent?.trim();
        let compactLabel = '';
        let hint = '';
        if (label === '手动策划' || label === '人工策划') {
          compactLabel = '人';
          hint = '人：手动策划';
        } else if (label === '自动策划' || label === 'AI 自动策划') {
          compactLabel = 'AI';
          hint = 'AI：自动策划';
        } else return;
        badge.textContent = compactLabel;
        badge.dataset.sourceHint = hint;
        badge.tabIndex = 0;
        badge.setAttribute('aria-label', hint);
      });
    },
    compactAccountHistoryPeriodLabels() {
      this.withinApp('.account-history-batch-head b').forEach(label => {
        if (label.dataset.periodRange) return;
        const value = label.textContent?.trim() || '';
        const match = value.match(/^(.*?周)\s*·\s*(\d{4}-\d{2}-\d{2})\s*至\s*(\d{4}-\d{2}-\d{2})$/);
        if (!match) return;
        const [, periodLabel, start, end] = match;
        const range = `${start} 至 ${end}`;
        label.textContent = periodLabel;
        label.dataset.periodRange = range;
        label.classList.add('ux-account-period-label');
        label.tabIndex = 0;
        label.setAttribute('aria-label', `${periodLabel}，${range}`);
      });
    },
    enhancePlanTopicDetailTriggers() {
      this.withinApp('.account-week-plan-card').forEach(card => {
        const title = card.querySelector('h3');
        if (!title) return;
        const topicTitle = title.textContent?.trim() || '未命名选题';
        card.setAttribute('aria-label', `查看单条策划：${topicTitle}`);
        title.classList.add('ux-topic-detail-trigger');
        if (title.dataset.planDetailTrigger === 'true') return;
        title.dataset.planDetailTrigger = 'true';
        title.addEventListener('click', event => {
          event.stopPropagation();
          card.click();
        });
      });
    },
    accountTypeLabel(profile) {
      return profile?.account_type || (profile?.certified === true ? '认证' : profile?.certified === false ? '非认证' : '—');
    },
    ensureAccountProfiles() {
      this.profileAttempted = true;
      if (this.profileRequest) return this.profileRequest;
      this.profileRequest = api.accounts(1000, true).then(accounts => {
        this.accountProfiles.clear();
        accounts.forEach(account => this.accountProfiles.set(account.account_id, account));
      }).catch(() => {
        this.profileRequest = undefined;
      });
      return this.profileRequest;
    },
    createMetaSpan(text, className) {
      const span = document.createElement('span');
      if (className) span.className = className;
      span.textContent = text;
      return span;
    },
    enhanceBatchAccountCards() {
      const cards = this.withinApp('.planning-account-groups .planning-account-group');
      if (!cards.length) return;
      cards.forEach(card => {
        card.classList.add('ux-account-card');
        const head = card.querySelector('.planning-account-group-head');
        const nameRow = head?.querySelector('.batch-account-name');
        const titleButton = nameRow?.querySelector('.account-detail-link');
        const idTag = nameRow?.querySelector('.tag.gray');
        const actions = head?.querySelector('.batch-account-head-actions');
        const expandButton = actions?.querySelector('.batch-account-expand');
        if (!head || !nameRow || !titleButton || !idTag || !actions || !expandButton) return;
        const accountId = idTag.textContent?.trim() || '';
        const accountName = titleButton.textContent?.trim() || accountId;
        const profile = this.accountProfiles.get(accountId);
        const identityWrap = nameRow.parentElement;
        const profileSignature = [accountId, accountName, this.accountTypeLabel(profile), profile?.organization || '', profile?.um_no || '', profile?.platform || '', profile?.persona || ''].join('|');
        identityWrap.classList.add('ux-account-identity');
        nameRow.classList.add('ux-account-title-row');
        idTag.classList.add('ux-original-account-id');
        identityWrap.parentElement?.classList.add('ux-account-main');
        if (card.dataset.profileSignature !== profileSignature) {
          let avatar = head.querySelector('.ux-account-avatar');
          if (!avatar) {
            avatar = document.createElement('div');
            avatar.className = 'ux-account-avatar';
            avatar.setAttribute('aria-hidden', 'true');
            identityWrap.parentElement?.insertBefore(avatar, identityWrap);
          }
          avatar.textContent = (accountName || '账').slice(0, 1).toLocaleUpperCase();
          let typeTag = nameRow.querySelector('.ux-account-type');
          if (!typeTag) {
            typeTag = document.createElement('span');
            typeTag.className = 'ux-account-type';
            titleButton.insertAdjacentElement('afterend', typeTag);
          }
          typeTag.textContent = this.accountTypeLabel(profile);
          let meta = identityWrap.querySelector('.ux-account-meta');
          if (!meta) {
            meta = document.createElement('div');
            meta.className = 'ux-account-meta';
            nameRow.insertAdjacentElement('afterend', meta);
          }
          meta.replaceChildren(this.createMetaSpan(accountId, 'ux-account-id'));
          if (profile?.organization) meta.append(this.createMetaSpan(profile.organization));
          if (profile?.um_no) meta.append(this.createMetaSpan(`UM ${profile.um_no}`));
          if (profile?.platform) meta.append(this.createMetaSpan(profile.platform));
          let persona = identityWrap.querySelector('.ux-account-persona');
          if (!persona) {
            persona = document.createElement('div');
            persona.className = 'ux-account-persona';
            persona.innerHTML = '<small>人设</small><span></span>';
            meta.insertAdjacentElement('afterend', persona);
          }
          const personaValue = persona.querySelector('span');
          if (personaValue) personaValue.textContent = profile?.persona || '未配置';
          card.dataset.profileSignature = profileSignature;
        }
        const countTag = actions.querySelector('.tag.blue');
        if (countTag) {
          countTag.classList.add('ux-plan-count');
          const count = countTag.textContent?.match(/\d+/)?.[0];
          const nextCountLabel = count ? `${count} 条策划` : countTag.textContent?.trim() || '';
          if (countTag.textContent?.trim() !== nextCountLabel) countTag.textContent = nextCountLabel;
        }
        let buttonLabel = expandButton.querySelector('.ux-expand-label');
        if (!buttonLabel) {
          buttonLabel = document.createElement('span');
          buttonLabel.className = 'ux-expand-label';
          expandButton.insertBefore(buttonLabel, expandButton.firstChild);
        }
        const nextButtonLabel = expandButton.getAttribute('aria-expanded') === 'true' ? '收起计划' : '查看计划';
        if (buttonLabel.textContent !== nextButtonLabel) buttonLabel.textContent = nextButtonLabel;
      });
      if (!this.profileAttempted) void this.ensureAccountProfiles().then(() => this.enhanceBatchAccountCards());
    },
    enhanceResultsUi() {
      this.compactPlanningSourceBadges();
      this.compactAccountHistoryPeriodLabels();
      this.enhancePlanTopicDetailTriggers();
      this.enhanceBatchAccountCards();
    }
  },
  created() {
    this.workspace = createWorkspaceTabs(this, !this.embedded);
    bindPageActivity(this, () => {
      if (!this.store.initialized) void this.store.initialize();
      this.enhanceResultsUi();
      this.resultsUiObserver = new MutationObserver(() => this.enhanceResultsUi());
      if (this.appRoot) this.resultsUiObserver.observe(this.appRoot, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['aria-expanded']
      });
    }, () => this.resultsUiObserver?.disconnect());
  },
  provide() {
    return {
      [workspaceKey]: this.embedded ? null : {
        registerCloseGuard: (...args) => this.workspace.registerCloseGuard(...args)
      }
    };
  }
};
</script>

<template>
  <div ref="appRoot" class="app-shell">
      <aside v-if="!embedded" class="sidebar">
        <div class="sidebar-brand"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="m6 18 9-9m-5-4 1-3 1 3 3 1-3 1-1 3-1-3-3-1zM17 14l1-2 1 2 2 1-2 1-1 2-1-2-2-1z" /></svg></span><strong>多账号智能策划</strong></div>
        <div class="sidebar-title">运营工作台</div>
        <nav aria-label="一级功能导航">
          <RouterLink v-for="item in nav" :key="item.to" :to="workspaceLocation(item.to)" active-class="" exact-active-class="" :class="['nav-item', { 'router-link-active': item.to === activeNav }]" :aria-current="item.to === activeNav ? 'page' : undefined">
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="item.icon" /></svg><span>{{ item.label }}</span>
          </RouterLink>
        </nav>
        <div class="sidebar-foot"><span :class="['status-dot', { online: store.databaseReady }]" />{{ store.connectionMessage }}</div>
      </aside>
    <div class="app-main-shell">
      <header v-if="!embedded" class="topbar"><WorkspaceTabs :tabs="workspaceTabs" :active="activeNav" :busy="workspaceClosing" @select="selectWorkspace" @close="closeWorkspace" /></header>
      <main id="workspace-page" class="main">
        <div v-if="store.initialized && !store.databaseReady" class="banner warning-banner" role="status">
          {{ store.connectionMessage }}
        </div>
        <RouterView v-if="embedded" /><keep-alive v-else :include="workspaceCacheNames"><RouterView :key="$route.path" /></keep-alive>
      </main>
    </div>
  </div>
</template>

<style>
:where(.planning-ui) .account-week-plan-tags .tag.gray[data-source-hint],:where(.planning-ui) .ux-account-period-label[data-period-range]{position:relative;cursor:help}
:where(.planning-ui) .account-week-plan-tags .tag.gray[data-source-hint]::after,:where(.planning-ui) .ux-account-period-label[data-period-range]::after{position:absolute;z-index:1300;bottom:calc(100% + 8px);left:50%;width:max-content;max-width:240px;padding:7px 9px;border:1px solid var(--neutral-200);border-radius:7px;background:var(--surface);box-shadow:var(--shadow-3);color:var(--neutral-700);font-size:12px;font-weight:400;line-height:18px;opacity:0;pointer-events:none;transform:translate(-50%,4px);transition:opacity .12s ease,transform .12s ease;white-space:nowrap}
:where(.planning-ui) .account-week-plan-tags .tag.gray[data-source-hint]::after{content:attr(data-source-hint)}
:where(.planning-ui) .ux-account-period-label[data-period-range]::after{content:attr(data-period-range)}
:where(.planning-ui) .account-week-plan-tags .tag.gray[data-source-hint]:hover::after,:where(.planning-ui) .account-week-plan-tags .tag.gray[data-source-hint]:focus-visible::after,:where(.planning-ui) .ux-account-period-label[data-period-range]:hover::after,:where(.planning-ui) .ux-account-period-label[data-period-range]:focus-visible::after{opacity:1;transform:translate(-50%,0)}
:where(.planning-ui) .account-week-plan-tags .tag.gray[data-source-hint]:focus-visible,:where(.planning-ui) .ux-account-period-label[data-period-range]:focus-visible{outline:2px solid var(--primary-300);outline-offset:2px;border-radius:4px}

:where(.planning-ui) .account-week-plan-card .ux-topic-detail-trigger{position:relative;cursor:pointer;transition:color .14s ease}
:where(.planning-ui) .account-week-plan-card .ux-topic-detail-trigger::after{margin-left:6px;color:var(--primary-600);content:'查看详情';font-size:10px;font-weight:500;opacity:.62;white-space:nowrap}
:where(.planning-ui) .account-week-plan-card .ux-topic-detail-trigger:hover{color:var(--primary-600)}

:where(.planning-ui) .planning-account-groups{display:grid!important;gap:14px!important;padding:0 20px 20px!important}
:where(.planning-ui) .planning-account-groups .planning-account-group.ux-account-card{overflow:hidden;margin:0!important;border:1px solid var(--neutral-200)!important;border-radius:14px!important;background:var(--surface)!important;box-shadow:0 1px 2px rgba(15,23,42,.03);transition:border-color .16s ease,box-shadow .16s ease}
:where(.planning-ui) .planning-account-groups .planning-account-group.ux-account-card:hover{border-color:var(--neutral-300)!important;box-shadow:0 7px 24px rgba(15,23,42,.055)}
:where(.planning-ui) .planning-account-groups .ux-account-card .planning-account-group-head{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:22px!important;min-height:0!important;padding:18px 20px!important;background:var(--surface)!important}
:where(.planning-ui) .planning-account-groups .ux-account-main{display:flex!important;align-items:flex-start!important;gap:14px!important;min-width:0!important;flex:1 1 auto}
:where(.planning-ui) .planning-account-groups .ux-account-avatar{display:grid;place-items:center;flex:0 0 42px;width:42px;height:42px;border-radius:12px;background:var(--primary-50);color:var(--primary-600);font-size:16px;font-weight:700}
:where(.planning-ui) .planning-account-groups .ux-account-identity{display:flex!important;flex-direction:column;gap:7px!important;min-width:0}
:where(.planning-ui) .planning-account-groups .ux-account-title-row{display:flex!important;align-items:center!important;flex-wrap:wrap!important;gap:8px!important}
:where(.planning-ui) .planning-account-groups .ux-account-title-row .account-detail-link{color:var(--neutral-900)!important;font-size:15px!important;font-weight:650!important;line-height:22px!important}
:where(.planning-ui) .planning-account-groups .ux-account-title-row .account-detail-link:hover{color:var(--primary-600)!important}
:where(.planning-ui) .planning-account-groups .ux-original-account-id{display:none!important}
:where(.planning-ui) .planning-account-groups .ux-account-type{display:inline-flex;align-items:center;height:22px;padding:0 8px;border:1px solid var(--primary-100);border-radius:6px;background:var(--primary-50);color:var(--primary-600);font-size:11px;font-weight:500;line-height:20px;white-space:nowrap}
:where(.planning-ui) .planning-account-groups .ux-account-meta{display:flex;align-items:center;flex-wrap:wrap;color:var(--neutral-400);font-size:11px;line-height:18px}
:where(.planning-ui) .planning-account-groups .ux-account-meta span{display:inline-flex;align-items:center}
:where(.planning-ui) .planning-account-groups .ux-account-meta span+span::before{width:1px;height:11px;margin:0 9px;background:var(--neutral-200);content:''}
:where(.planning-ui) .planning-account-groups .ux-account-id{font-variant-numeric:tabular-nums}
:where(.planning-ui) .planning-account-groups .ux-account-persona{display:flex;align-items:center;gap:7px;min-width:0}
:where(.planning-ui) .planning-account-groups .ux-account-persona small{flex:none;padding:2px 6px;border-radius:5px;background:var(--neutral-100);color:var(--neutral-500);font-size:10px;line-height:16px}
:where(.planning-ui) .planning-account-groups .ux-account-persona span{max-width:520px;overflow:hidden;color:var(--neutral-600);font-size:12px;line-height:18px;text-overflow:ellipsis;white-space:nowrap}
:where(.planning-ui) .planning-account-groups .ux-account-card .batch-account-head-actions{display:flex!important;align-items:center!important;gap:10px!important;flex:none}
:where(.planning-ui) .planning-account-groups .ux-plan-count{height:24px;padding:0 9px!important;border-radius:6px!important;font-size:11px!important;line-height:24px!important}
:where(.planning-ui) .planning-account-groups .ux-account-card .batch-account-expand{display:inline-flex!important;align-items:center!important;gap:6px!important;width:auto!important;height:34px!important;padding:0 10px!important;border-color:var(--neutral-200)!important;border-radius:8px!important;color:var(--neutral-600)!important}
:where(.planning-ui) .planning-account-groups .ux-account-card .batch-account-expand:hover{border-color:var(--primary-200)!important;background:var(--primary-50)!important;color:var(--primary-600)!important}
:where(.planning-ui) .planning-account-groups .ux-expand-label{font-size:12px;line-height:18px;white-space:nowrap}
:where(.planning-ui) .planning-account-groups .ux-account-card>.account-week-carousel{margin:0!important;padding:16px 18px 18px!important;border-top:1px solid var(--neutral-100);background:linear-gradient(180deg,var(--neutral-50),var(--surface) 76px)}
:where(.planning-ui) .planning-account-groups .ux-account-card .account-week-calendar{padding:0!important}
:where(.planning-ui) .planning-account-groups .ux-account-card .account-week-day{border-radius:10px!important;background:var(--surface)!important;box-shadow:0 1px 2px rgba(15,23,42,.025)}
:where(.planning-ui) .planning-account-groups .ux-account-card .account-week-plan-card{border-radius:8px!important;transition:border-color .14s ease,box-shadow .14s ease,transform .14s ease}
:where(.planning-ui) .planning-account-groups .ux-account-card .account-week-plan-card:hover{border-color:var(--primary-200)!important;box-shadow:0 5px 16px rgba(15,23,42,.06);transform:translateY(-1px)}

@media(max-width:900px){
  :where(.planning-ui) .planning-account-groups{padding:0 12px 16px!important}
  :where(.planning-ui) .planning-account-groups .ux-account-card .planning-account-group-head{align-items:flex-start!important;flex-direction:column!important;padding:16px!important}
  :where(.planning-ui) .planning-account-groups .ux-account-card .batch-account-head-actions{width:100%;justify-content:space-between!important}
  :where(.planning-ui) .planning-account-groups .ux-account-persona span{max-width:420px}
}
@media(max-width:580px){
  :where(.planning-ui) .planning-account-groups .ux-account-main{gap:10px!important}
  :where(.planning-ui) .planning-account-groups .ux-account-avatar{width:36px;height:36px;flex-basis:36px;border-radius:10px}
  :where(.planning-ui) .planning-account-groups .ux-account-persona span{max-width:230px}
  :where(.planning-ui) .planning-account-groups .ux-account-card>.account-week-carousel{padding:12px 8px 14px!important}
}
</style>
