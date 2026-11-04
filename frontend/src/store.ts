import Vue from 'vue'
import Vuex, { type Module, type Store } from 'vuex'
import { api } from './api'
import type { BatchSummary, ConfigResponse, ManualPlanInput, StrategyConfig } from './types'
import type { ManualTaskListState } from './ui/manualTask'

export const defaultConfig: StrategyConfig = {
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
}

Vue.use(Vuex)
const createState = () => ({
  initialized: false,
  manualCreating: false,
  manualTaskListState: null as ManualTaskListState | null,
  resultAccountListState: null as { page: number; pageSize: number; draft: Record<string, unknown>; applied: Record<string, unknown> } | null,
  databaseReady: false,
  connectionMessage: '正在连接服务…',
  config: structuredClone(defaultConfig) as StrategyConfig,
  configVersion: 0,
  configUpdatedAt: null as string | null,
  configIsDemo: false,
  batches: [] as BatchSummary[],
})
type PlanningState = ReturnType<typeof createState>

export const planningModule: Module<PlanningState, unknown> = {
  namespaced: true,
  state: createState,
  mutations: {
    set(state, payload: { key: keyof PlanningState; value: unknown }) { Vue.set(state, payload.key, payload.value) },
    applyConfig(state, result: ConfigResponse) {
      state.config = result.config
      state.configVersion = result.version
      state.configUpdatedAt = result.updated_at
      state.configIsDemo = result.is_demo
    },
  },
  actions: {
    async initialize({ state, commit, dispatch }) {
      try {
        const health = await api.health()
        commit('set', { key: 'databaseReady', value: health.database === 'ok' })
        commit('set', { key: 'connectionMessage', value: state.databaseReady ? '数据库已连接' : '数据库暂不可用，页面为只读预览' })
      } catch {
        commit('set', { key: 'databaseReady', value: false })
        commit('set', { key: 'connectionMessage', value: '后端未启动，页面为只读预览' })
      }
      if (state.databaseReady) {
        const results = await Promise.allSettled([dispatch('refreshConfig')])
        if (results.some(result => result.status === 'rejected')) {
          commit('set', { key: 'connectionMessage', value: '数据库已连接，部分页面数据加载失败' })
        }
      }
      commit('set', { key: 'initialized', value: true })
    },
    async refreshConfig({ commit }) {
      commit('applyConfig', await api.config())
    },
    async saveConfig({ state, commit }, config: StrategyConfig) {
      commit('applyConfig', await api.saveConfig(config, state.configVersion))
    },
    async saveConfigModule({ state, commit }, payload: { module: 'marketing' | 'strategy'; config: StrategyConfig }) {
      commit('applyConfig', await api.saveConfigModule(payload.module, payload.config, state.configVersion))
    },
    async restoreConfigModule({ state, commit }, payload: { module: 'marketing' | 'strategy'; version: number }) {
      commit('applyConfig', await api.restoreConfigModule(payload.module, payload.version, state.configVersion))
    },
    async restoreConfig({ state, commit }, version: number) {
      commit('applyConfig', await api.restoreConfig(version, state.configVersion))
    },
    async refreshBatches({ commit }) {
      commit('set', { key: 'batches', value: await api.batches() })
    },
    async createManual({ dispatch }, input: ManualPlanInput) {
      const result = await api.createManual(input)
      await dispatch('refreshBatches')
      return result
    },
  },
}

export const planningStore = new Vuex.Store({ modules: { stratMatrix: planningModule } })
let activeStore: Store<any> = planningStore
let namespace = 'stratMatrix'
/** Call before mounting when embedding in the bank's existing Vuex store. */
export function attachPlanningStore(host: Store<any>, moduleName = 'stratMatrix') {
  if (!host.hasModule(moduleName)) host.registerModule(moduleName, planningModule)
  activeStore = host
  namespace = moduleName
}
const dispatch = (name: string, payload?: unknown) => activeStore.dispatch(`${namespace}/${name}`, payload)
const facade = {
  initialize: (): Promise<void> => dispatch('initialize'),
  refreshConfig: (): Promise<void> => dispatch('refreshConfig'),
  applyConfig: (result: ConfigResponse) => activeStore.commit(`${namespace}/applyConfig`, result),
  saveConfig: (config: StrategyConfig): Promise<void> => dispatch('saveConfig', config),
  saveConfigModule: (module: 'marketing' | 'strategy', config: StrategyConfig): Promise<void> => dispatch('saveConfigModule', { module, config }),
  restoreConfigModule: (module: 'marketing' | 'strategy', version: number): Promise<void> => dispatch('restoreConfigModule', { module, version }),
  restoreConfig: (version: number): Promise<void> => dispatch('restoreConfig', version),
  refreshBatches: (): Promise<void> => dispatch('refreshBatches'),
  createManual: (input: ManualPlanInput): ReturnType<typeof api.createManual> => dispatch('createManual', input),
}
for (const key of Object.keys(createState())) Object.defineProperty(facade, key, {
  enumerable: true,
  get: () => activeStore.state[namespace][key],
  set: value => activeStore.commit(`${namespace}/set`, { key, value }),
})
export const usePlanningStore = () => facade as typeof facade & PlanningState

