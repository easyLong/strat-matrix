import Vue from 'vue'
import VueRouter, { isNavigationFailure, type RawLocation, type Route } from 'vue-router'
import { getCurrentInstance } from './composition'
import { planningLocation, localPlanningPath } from '../host/runtime'

Vue.use(VueRouter)
export type RouteLocationRaw = RawLocation
const NativeRouterLink = Vue.component('RouterLink')
export const RouterLink = Vue.extend({
  name: 'PlanningRouterLink', functional: true,
  props: { to: { type: [String, Object], required: true } },
  render(h, context) {
    return h(NativeRouterLink, { ...context.data, props: { ...context.data.attrs, ...context.props,
      to: planningLocation(context.props.to as RawLocation) } }, context.children)
  },
})
export const RouterView = Vue.component('RouterView')
const routers = new WeakMap<VueRouter, VueRouter>()

export function useRouter(): VueRouter {
  const vm = getCurrentInstance()?.proxy
  if (!vm) throw new Error('路由只能在页面组件中使用')
  const router = vm.$router
  if (!routers.has(router)) routers.set(router, new Proxy(router, {
    get(target, key) {
      if (key === 'push' || key === 'replace') return (...args: any[]) => {
        const result = (target[key] as Function).apply(target, [planningLocation(args[0]), ...args.slice(1)])
        return result && typeof result.catch === 'function'
          ? result.catch((error: unknown) => { if (!isNavigationFailure(error)) throw error })
          : result
      }
      const value = Reflect.get(target, key)
      return typeof value === 'function' ? value.bind(target) : value
    },
  }))
  return routers.get(router)!
}

export function useRoute(): Route {
  const vm = getCurrentInstance()?.proxy
  if (!vm) throw new Error('路由只能在页面组件中使用')
  // Always read the current route; a snapshot would stop reacting after navigation.
  return new Proxy({} as Route, { get: (_, key) => key === 'path' ? localPlanningPath(vm.$route.path) : Reflect.get(vm.$route, key) })
}
