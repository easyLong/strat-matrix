import Vue from 'vue';
import { installPlanningUi } from './install';
import { attachPlanningStore } from './store';
import { setPlanningHttp } from './api/http';
import { configurePlanningRuntime } from './host/runtime';
import { createPlanningRoutes } from './host/routes';
/** Call once before mounting the host; register returned routes using its existing router. */
export function createPlanningIntegration(options) {
    if (!options.http || !options.store)
        throw new Error('宿主接入必须提供HTTP客户端和Vuex');
    if (!options.apiPrefix || !options.apiPrefix.startsWith('/'))
        throw new Error('请明确配置Java策划接口前缀');
    configurePlanningRuntime({ ...options, hosted: true });
    setPlanningHttp(options.http, options);
    installPlanningUi(Vue, { elementUI: options.installElementUI === true });
    attachPlanningStore(options.store, options.storeModule);
    return { routes: createPlanningRoutes(options.routePrefix.replace(/\/$/, '')) };
}
export { canPlanning } from './host/runtime';
export { PlanningRequestError } from './api/http';
