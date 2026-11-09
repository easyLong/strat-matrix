import { request } from './api/http';
import { queryManualTasks, queryPlanPage, queryAccountPage, queryPeriodPage, queryPeriodContext, queryResultFailures } from './api/queries';
function tagNameText(value) {
    if (typeof value === 'string')
        return value;
    if (value && typeof value === 'object') {
        const record = value;
        for (const key of ['name', 'label', 'value', 'title', 'text']) {
            if (key in record)
                return tagNameText(record[key]);
        }
        return JSON.stringify(value);
    }
    return value == null ? '' : String(value);
}
function normalizeTagTaxonomy(value) {
    const response = value && typeof value === 'object' ? value : {};
    const source = (response.items ?? response.tags);
    const items = {};
    for (const dimension of ['T1', 'T2', 'T3', 'T4', 'T5']) {
        const values = Array.isArray(source?.[dimension]) ? source[dimension] : [];
        items[dimension] = values.map(value => {
            if (typeof value === 'string')
                return { id: null, name: value, enabled: true };
            const item = value && typeof value === 'object' ? value : {};
            return {
                id: typeof item.id === 'string' ? item.id : null,
                name: tagNameText(item.name ?? item.label ?? item.value),
                enabled: typeof item.enabled === 'boolean' ? item.enabled : true,
                node_type: item.node_type === 'group' ? 'group' : 'tag',
                parent_id: typeof item.parent_id === 'string' ? item.parent_id : null,
            };
        }).filter(item => item.name.length > 0);
    }
    const tags = Object.fromEntries(Object.entries(items).map(([dimension, values]) => [
        dimension, values.filter(item => item.enabled && item.node_type !== 'group').map(item => item.name),
    ]));
    return {
        version: typeof response.version === 'number' ? response.version : 0,
        tags,
        items,
    };
}
const post = (path, body = {}) => request(path, { method: 'POST', body: JSON.stringify(body) });
async function allManualTasks(path) {
    const tasks = new Map();
    const limit = 100;
    for (let offset = 0;; offset += limit) {
        const rows = await post(`${path}/query`, { limit, offset });
        const previousSize = tasks.size;
        for (const row of rows)
            tasks.set(row.task_code, row);
        if (rows.length < limit)
            return [...tasks.values()];
        if (tasks.size === previousSize)
            throw new Error('任务分页读取异常，请重试');
    }
}
export const api = {
    health: () => request('/health', { method: 'GET' }),
    config: () => post('/config/query'),
    saveConfig: (config, expectedVersion) => post('/config/save', { config, expectedVersion }),
    configVersions: () => post('/config/versions/query'),
    restoreConfig: (version, expectedVersion) => post(`/config/versions/${version}/restore`, { expectedVersion }),
    tagTaxonomy: async () => normalizeTagTaxonomy(await post('/tag-taxonomy/query')),
    saveTagTaxonomy: async (items, expectedVersion) => normalizeTagTaxonomy(await post('/tag-taxonomy/save', { items, expected_version: expectedVersion })),
    accounts: (limit = 1000, includeDisabled = false) => post('/accounts/query', { limit, includeDisabled }),
    manualAccountAvailability: (publishDate) => post('/manual-plans/account-availability/query', { publishDate }),
    topics: () => post('/topics/query', { limit: 1000 }),
    topicDetail: (topicId, topicType) => post(`/topics/${encodeURIComponent(topicId)}/detail/query`, { topicType: topicType || undefined }),
    batches: (type, limit = 200) => post('/batches/query', { limit, planType: type }),
    batch: (id) => post(`/batches/${id}/query`),
    replacementCandidates: (itemId) => post(`/items/${itemId}/replacement-candidates/query`),
    replaceTopic: (itemId, newTopicId, expectedVersion, reason) => request(`/items/${itemId}/replace-topic`, { method: 'POST', body: JSON.stringify({ new_topic_id: newTopicId, expected_version: expectedVersion, reason }) }),
    adjustments: (itemId) => post(`/items/${itemId}/adjustments/query`),
    previewManual: (input) => request('/manual-plans/previews', { method: 'POST', body: JSON.stringify(input) }),
    submitManualPreview: (previewId) => request(`/manual-plans/previews/${encodeURIComponent(previewId)}/submit`, { method: 'POST' }),
    manualTaskPage: queryManualTasks,
    planPage: queryPlanPage,
    accountPage: queryAccountPage,
    periodPage: queryPeriodPage,
    periodContext: queryPeriodContext,
    resultFailures: queryResultFailures,
    manualTasks: () => allManualTasks('/manual-plans/tasks'),
    marketingTasks: () => allManualTasks('/manual-plans/marketing-tasks'),
    createMarketingTask: (input) => request('/manual-plans/marketing-tasks', { method: 'POST', body: JSON.stringify(input) }),
    marketingTaskDetails: (code) => post(`/manual-plans/marketing-tasks/${encodeURIComponent(code)}/query`),
};
