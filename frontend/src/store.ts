import { defineStore } from 'pinia'
import { api } from './api'
import type { BatchSummary, ConfigResponse, ManualPlanInput, StrategyConfig } from './types'

export const defaultConfig: StrategyConfig = {
  marketing_max: 1,
  planning_days: [1, 3, 5],
  schedule_day: 2,
  schedule_time: '22:00',
  hotspot_ratio: 20,
  rolling_posts: 10,
  stage_targets: [
    { name: '冷启验证期', traffic: 80, conversion: 20 },
    { name: '流量增长期', traffic: 70, conversion: 30 },
    { name: '转化试探期', traffic: 50, conversion: 50 },
    { name: '转化放大期', traffic: 30, conversion: 70 },
    { name: '稳定经营期', traffic: 50, conversion: 50 },
  ],
  lifecycle_rules: [
    { name: '稳定经营期', conditions: [{ field: 'followers_count', operator: 'gte', value: 100000, join: 'AND' }, { field: 'rolling_interaction_count', operator: 'gte', value: 100, join: 'AND' }], catchAll: false },
    { name: '转化放大期', conditions: [{ field: 'followers_count', operator: 'gte', value: 50000, join: 'AND' }, { field: 'rolling_interaction_count', operator: 'gte', value: 100, join: 'AND' }], catchAll: false },
    { name: '转化试探期', conditions: [{ field: 'rolling_interaction_count', operator: 'gte', value: 100, join: 'AND' }], catchAll: false },
    { name: '流量增长期', conditions: [{ field: 'valid_content_count', operator: 'gte', value: 10, join: 'AND' }], catchAll: false },
    { name: '冷启验证期', conditions: [], catchAll: true },
  ],
}

export const usePlanningStore = defineStore('planning', {
  state: () => ({
    databaseReady: false,
    connectionMessage: '正在连接服务…',
    config: structuredClone(defaultConfig) as StrategyConfig,
    configVersion: 0,
    configUpdatedAt: null as string | null,
    configIsDemo: false,
    batches: [] as BatchSummary[],
  }),
  actions: {
    async initialize() {
      try {
        const health = await api.health()
        this.databaseReady = health.database === 'ok'
        this.connectionMessage = this.databaseReady ? '数据库已连接' : '数据库暂不可用，页面为只读预览'
      } catch {
        this.databaseReady = false
        this.connectionMessage = '后端未启动，页面为只读预览'
      }
      if (this.databaseReady) {
        const results = await Promise.allSettled([this.refreshConfig(), this.refreshBatches()])
        if (results.some(result => result.status === 'rejected')) {
          this.connectionMessage = '数据库已连接，部分页面数据加载失败'
        }
      }
    },
    async refreshConfig() {
      const result = await api.config()
      this.applyConfig(result)
    },
    applyConfig(result: ConfigResponse) {
      this.config = result.config
      this.configVersion = result.version
      this.configUpdatedAt = result.updated_at
      this.configIsDemo = result.is_demo
    },
    async saveConfig(config: StrategyConfig) {
      this.applyConfig(await api.saveConfig(config, this.configVersion))
    },
    async saveConfigModule(module: 'marketing' | 'strategy', config: StrategyConfig) {
      this.applyConfig(await api.saveConfigModule(module, config, this.configVersion))
    },
    async restoreConfigModule(module: 'marketing' | 'strategy', version: number) {
      this.applyConfig(await api.restoreConfigModule(module, version, this.configVersion))
    },
    async restoreConfig(version: number) {
      this.applyConfig(await api.restoreConfig(version, this.configVersion))
    },
    async refreshBatches() {
      this.batches = await api.batches()
    },
    async createManual(input: ManualPlanInput) {
      const result = await api.createManual(input)
      await this.refreshBatches()
      return result
    },
  },
})

