import Vue from 'vue';
export const planningRuntime = Vue.observable({
    hosted: false,
    routePrefix: '',
    can: undefined,
    notify: undefined,
});
export function configurePlanningRuntime(options = {}) {
    const prefix = (options.routePrefix || '').replace(/\/$/, '');
    if (prefix && (!prefix.startsWith('/') || /[?#%\\]|\/\//.test(prefix) || prefix.split('/').some(p => p === '..' || p === '.')))
        throw new Error('策划模块路由前缀无效');
    if (options.hosted && (!prefix || typeof options.can !== 'function'))
        throw new Error('宿主接入必须配置路由前缀和权限判断');
    Object.assign(planningRuntime, { hosted: Boolean(options.hosted), routePrefix: prefix,
        can: options.can, notify: options.notify });
}
export function canPlanning(permission) {
    return planningRuntime.can ? planningRuntime.can(permission) === true : !planningRuntime.hosted;
}
export function requirePlanning(permission) {
    if (!canPlanning(permission)) {
        const error = new Error('没有此操作的权限');
        error.name = 'PlanningPermissionError';
        throw error;
    }
}
const localPaths = ['/config', '/manual', '/results', '/auto'];
export function localPlanningPath(path) {
    const prefix = planningRuntime.routePrefix;
    if (prefix && (path === prefix || path.startsWith(prefix + '/')))
        return path.slice(prefix.length) || '/';
    return path;
}
export function planningLocation(location) {
    const prefix = planningRuntime.routePrefix;
    const map = (path) => {
        const match = path.match(/^([^?#]*)([?#].*)?$/);
        return prefix && localPaths.includes(match[1]) ? prefix + path : path;
    };
    return typeof location === 'string' ? map(location)
        : location.path ? { ...location, path: map(location.path) } : location;
}
export function localPlanningRoute(route) {
    return new Proxy(route, { get: (target, key) => key === 'path' ? localPlanningPath(target.path) : Reflect.get(target, key) });
}
export function authorizePlanningRequest(path, method) {
    if (!planningRuntime.hosted)
        return;
    const url = path.split('?')[0];
    if (url === '/health')
        return;
    const read = method === 'POST' && /\/query$/.test(url);
    // Shared bootstrap config is needed by manual planning too; history and
    // page navigation still require config.view, writes require their own capability.
    if (url === '/config/query' && read
        && ['config.view', 'manual.view', 'results.view'].some(canPlanning))
        return;
    let permission;
    if (url.startsWith('/config'))
        permission = /\/restore$/.test(url) ? 'config.restore' : read ? 'config.view' : 'config.edit';
    else if (url.startsWith('/tag-taxonomy') && !read)
        permission = 'config.edit';
    else if (url === '/query/export')
        permission = 'results.export';
    else if (/\/replace-topic$|\/replacement-candidates(?:\/query)?$/.test(url))
        permission = 'results.replace';
    else if (url.startsWith('/manual-plans') || url === '/batches/manual')
        permission = read ? 'manual.view' : 'manual.create';
    else if (url === '/query/manual-tasks')
        permission = 'manual.view';
    else if (url.startsWith('/query/') || url.startsWith('/batches') || url.startsWith('/items') || url.startsWith('/planning-'))
        permission = 'results.view';
    if (permission)
        requirePlanning(permission);
    else if (!['config.view', 'manual.view', 'results.view'].some(canPlanning))
        requirePlanning('results.view');
}
