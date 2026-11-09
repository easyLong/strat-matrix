import { request } from './http';
export function queryManualTasks(query, signal) {
    return request('/query/manual-tasks', {
        method: 'POST', body: JSON.stringify(query), signal,
    });
}
export function queryPlanPage(query, signal) {
    return request('/query/plans', { method: 'POST', body: JSON.stringify(query), signal });
}
export function queryAccountPage(query, signal) {
    return request('/query/accounts', { method: 'POST', body: JSON.stringify(query), signal });
}
export function queryPeriodPage(query, signal) {
    return request('/query/periods', { method: 'POST', body: JSON.stringify(query), signal });
}
export function queryPeriodContext(query) {
    return request('/query/period-context', { method: 'POST', body: JSON.stringify(query) });
}
export function queryResultFailures(query, signal) {
    return request('/query/failures', { method: 'POST', body: JSON.stringify(query), signal });
}
