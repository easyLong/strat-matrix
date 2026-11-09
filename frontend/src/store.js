import Vue from 'vue';
import Vuex from 'vuex';
import { api } from './api';
export const defaultConfig = {
    marketing_max: 1,
    planning_days: [1, 3, 5],
    schedule_day: 2,
    schedule_time: '22:00',
    hotspot_ratio: 20,
    rolling_posts: 10,
    stage_targets: [
        { name: '冷启动期', traffic: 80, conversion: 20 },
        { name: '流量增长期', traffic: 70, conversion: 30 },
        { name: '转化试探期', traffic: 50, conversion: 50 },
        { name: '转化放大期', traffic: 30, conversion: 70 },
        { name: '稳定经营期', traffic: 50, conversion: 50 },
    ],
    lifecycle_rules: [
        { name: '稳定经营期', conditions: [{ field: 'followers_count', operator: 'gte', value: 500, join: 'AND' }, { field: 'rolling_interaction_count', operator: 'gte', value: 20, join: 'AND' }, { field: 'valid_content_count', operator: 'gte', value: 5, join: 'AND' }], catchAll: false },
        { name: '转化放大期', conditions: [{ field: 'followers_count', operator: 'gte', value: 200, join: 'AND' }, { field: 'rolling_interaction_count', operator: 'gte', value: 10, join: 'AND' }, { field: 'valid_content_count', operator: 'gte', value: 5, join: 'AND' }], catchAll: false },
        { name: '转化试探期', conditions: [{ field: 'followers_count', operator: 'gte', value: 100, join: 'AND' }, { field: 'rolling_interaction_count', operator: 'gte', value: 5, join: 'AND' }, { field: 'valid_content_count', operator: 'gte', value: 5, join: 'AND' }], catchAll: false },
        { name: '流量增长期', conditions: [{ field: 'followers_count', operator: 'gte', value: 50, join: 'AND' }, { field: 'valid_content_count', operator: 'gte', value: 5, join: 'OR' }], catchAll: false },
        { name: '冷启动期', conditions: [], catchAll: true },
    ],
};
Vue.use(Vuex);
const createState = () => ({
    initialized: false,
    manualCreating: false,
    manualTaskListState: null,
    resultAccountListState: null,
    databaseReady: false,
    connectionMessage: '正在连接服务…',
    config: structuredClone(defaultConfig),
    configVersion: 0,
    configUpdatedAt: null,
    configIsDemo: false,
    batches: [],
});
export const planningModule = {
    namespaced: true,
    state: createState,
    mutations: {
        set(state, payload) { Vue.set(state, payload.key, payload.value); },
        applyConfig(state, result) {
            state.config = result.config;
            state.configVersion = result.version;
            state.configUpdatedAt = result.updated_at;
            state.configIsDemo = result.is_demo;
        },
    },
    actions: {
        async initialize({ state, commit, dispatch }) {
            try {
                const health = await api.health();
                commit('set', { key: 'databaseReady', value: health.database === 'ok' });
                commit('set', { key: 'connectionMessage', value: state.databaseReady ? '数据库已连接' : '数据库暂不可用，页面为只读预览' });
            }
            catch {
                commit('set', { key: 'databaseReady', value: false });
                commit('set', { key: 'connectionMessage', value: '后端未启动，页面为只读预览' });
            }
            if (state.databaseReady) {
                const results = await Promise.allSettled([dispatch('refreshConfig')]);
                if (results.some(result => result.status === 'rejected')) {
                    commit('set', { key: 'connectionMessage', value: '数据库已连接，部分页面数据加载失败' });
                }
            }
            commit('set', { key: 'initialized', value: true });
        },
        async refreshConfig({ commit }) {
            commit('applyConfig', await api.config());
        },
        async saveConfig({ state, commit }, config) {
            commit('applyConfig', await api.saveConfig(config, state.configVersion));
        },
        async restoreConfig({ state, commit }, version) {
            commit('applyConfig', await api.restoreConfig(version, state.configVersion));
        },
        async refreshBatches({ commit }) {
            commit('set', { key: 'batches', value: await api.batches() });
        },
    },
};
export const planningStore = new Vuex.Store({ modules: { stratMatrix: planningModule } });
let activeStore = planningStore;
let namespace = 'stratMatrix';
/** Call before mounting when embedding in the bank's existing Vuex store. */
export function attachPlanningStore(host, moduleName = 'stratMatrix') {
    if (!host.hasModule(moduleName))
        host.registerModule(moduleName, planningModule);
    activeStore = host;
    namespace = moduleName;
}
const dispatch = (name, payload) => activeStore.dispatch(`${namespace}/${name}`, payload);
const facade = {
    initialize: () => dispatch('initialize'),
    refreshConfig: () => dispatch('refreshConfig'),
    applyConfig: (result) => activeStore.commit(`${namespace}/applyConfig`, result),
    saveConfig: (config) => dispatch('saveConfig', config),
    restoreConfig: (version) => dispatch('restoreConfig', version),
    refreshBatches: () => dispatch('refreshBatches'),
};
for (const key of Object.keys(createState()))
    Object.defineProperty(facade, key, {
        enumerable: true,
        get: () => activeStore.state[namespace][key],
        set: value => activeStore.commit(`${namespace}/set`, { key, value }),
    });
export const usePlanningStore = () => facade;
