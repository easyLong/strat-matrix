import Vue from 'vue'
import type { Store } from 'vuex'
import { installPlanningUi } from './install'
import { attachPlanningStore } from './store'
import { setPlanningHttp, type PlanningHttpClient, type PlanningHttpOptions } from './api/http'
import { configurePlanningRuntime, type PlanningRuntimeOptions } from './host/runtime'
import { createPlanningRoutes } from './host/routes'

export interface PlanningHostOptions extends PlanningHttpOptions {
  http: PlanningHttpClient
  store: Store<any>
  routePrefix: string
  apiPrefix: string
  can: NonNullable<PlanningRuntimeOptions['can']>
  notify?: PlanningRuntimeOptions['notify']
  storeModule?: string
  /** The host normally already owns Element UI; do not register/load its theme twice. */
  installElementUI?: boolean
}

/** Call once before mounting the host; register returned routes using its existing router. */
export function createPlanningIntegration(options: PlanningHostOptions) {
  if (!options.http || !options.store) throw new Error('宿主接入必须提供HTTP客户端和Vuex')
  if (!options.apiPrefix || !options.apiPrefix.startsWith('/')) throw new Error('请明确配置Java策划接口前缀')
  configurePlanningRuntime({ ...options, hosted: true })
  setPlanningHttp(options.http, options)
  installPlanningUi(Vue, { elementUI: options.installElementUI === true })
  attachPlanningStore(options.store, options.storeModule)
  return { routes: createPlanningRoutes(options.routePrefix.replace(/\/$/, '')) }
}

export { canPlanning, type PlanningPermission } from './host/runtime'
export { PlanningRequestError } from './api/http'
