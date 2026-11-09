import Vue from 'vue';
import VueRouter, { isNavigationFailure } from 'vue-router';
import { planningLocation, localPlanningPath } from '../host/runtime';
Vue.use(VueRouter);
const NativeRouterLink = Vue.component('RouterLink');
export const RouterLink = Vue.extend({
    name: 'PlanningRouterLink', functional: true,
    props: { to: { type: [String, Object], required: true } },
    render(h, context) {
        return h(NativeRouterLink, { ...context.data, props: { ...context.data.attrs, ...context.props,
                to: planningLocation(context.props.to) } }, context.children);
    },
});
export const RouterView = Vue.component('RouterView');
const routers = new WeakMap();
export function planningRouter(vm) {
    const router = vm.$router;
    if (!routers.has(router))
        routers.set(router, new Proxy(router, {
            get(target, key) {
                if (key === 'push' || key === 'replace')
                    return (...args) => {
                        const result = target[key].apply(target, [planningLocation(args[0]), ...args.slice(1)]);
                        return result && typeof result.catch === 'function'
                            ? result.catch((error) => { if (!isNavigationFailure(error))
                                throw error; })
                            : result;
                    };
                const value = Reflect.get(target, key);
                return typeof value === 'function' ? value.bind(target) : value;
            },
        }));
    return routers.get(router);
}
export function planningRoute(vm) {
    // Always read the current route; a snapshot would stop reacting after navigation.
    return new Proxy({}, { get: (_, key) => key === 'path' ? localPlanningPath(vm.$route.path) : Reflect.get(vm.$route, key) });
}
