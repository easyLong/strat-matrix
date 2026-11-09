import Vue from 'vue';
import { planningRoute, planningRouter } from '../compat/router';
export const workspacePages = [{
  key: '/config',
  title: 'AI策划配置',
  component: 'PlanningConfigPage'
}, {
  key: '/manual',
  title: '人工策划',
  component: 'PlanningManualPage'
}, {
  key: '/results',
  title: '策划结果',
  component: 'PlanningResultsPage'
}];
export const workspaceKey = Symbol('planning-workspace');

/** The development shell owns these tabs; the bank host supplies its own cache. */
export function createWorkspaceTabs(owner, enabled) {
  const guards = new Map();
  const router = planningRouter(owner);
  const state = new Vue({
    data: () => ({
      tabs: [],
      closing: false
    }),
    computed: {
      route() {
        return planningRoute(owner);
      },
      cacheNames() {
        return this.tabs.map(tab => tab.component);
      }
    },
    methods: {
      registerCloseGuard(key, guard) {
        guards.set(key, guard);
        return () => {
          if (guards.get(key) === guard) guards.delete(key);
        };
      },
      locationFor(key) {
        return this.tabs.find(tab => tab.key === key)?.location || key;
      },
      async select(key) {
        if (!this.closing) await router.push(this.locationFor(key));
      },
      async close(key) {
        if (this.closing) return;
        const tab = this.tabs.find(tab => tab.key === key);
        if (!tab) return;
        this.closing = true;
        try {
          const guard = guards.get(key);
          if (guard?.dirty()) {
            if (this.route.path !== key) {
              await router.push(tab.location);
              await Vue.nextTick();
              if (this.route.path !== key) return;
            }
            if (!(await guard.confirm())) return;
          }
          if (this.route.path === key) {
            const index = this.tabs.indexOf(tab);
            const fallback = this.tabs[index - 1] || this.tabs[index + 1];
            await router.replace(fallback?.location || '/workspace');
            if (this.route.path === key) return;
          }
          this.tabs = this.tabs.filter(item => item.key !== key);
        } finally {
          this.closing = false;
        }
      }
    },
    created() {
      this.$watch(() => this.route.fullPath, location => {
        if (!enabled) return;
        const page = workspacePages.find(page => page.key === this.route.path);
        if (!page) return;
        const tab = this.tabs.find(tab => tab.key === page.key);
        if (tab) tab.location = location;else this.tabs.push({
          ...page,
          location
        });
      }, {
        immediate: true
      });
    },
    beforeDestroy() {
      guards.clear();
    }
  });
  owner.$once('hook:beforeDestroy', () => state.$destroy());
  return state;
}
