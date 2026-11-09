import ConfigView from '../views/ConfigView.vue';
import ManualView from '../views/ManualView.vue';
import ResultsHubView from '../views/ResultsHubView.vue';
import PlanningHostView from './PlanningHostView.vue';
import { canPlanning, planningRuntime } from './runtime';
export function createPlanningRoutes(prefix) {
    const pages = [
        ['config', 'AI策划配置', ConfigView, 'config.view'],
        ['manual', '人工策划', ManualView, 'manual.view'],
        ['results', '策划结果', ResultsHubView, 'results.view'],
    ];
    return [{ path: prefix, component: PlanningHostView, children: [
                { path: '', redirect: () => `${prefix}/${pages.find(page => canPlanning(page[3]))?.[0] || 'config'}` },
                ...pages.map(([path, title, component, permission]) => ({
                    path, name: `stratMatrix.${path}`, component,
                    meta: { title, planningPermission: permission, closable: true, keepAlive: true, tabKey: `${prefix}/${path}` },
                    beforeEnter: (_to, _from, next) => {
                        if (canPlanning(permission))
                            next();
                        else {
                            planningRuntime.notify?.('没有访问该页面的权限', 'error');
                            next(false);
                        }
                    },
                })),
                { path: 'auto', redirect: `${prefix}/results` },
            ] }];
}
