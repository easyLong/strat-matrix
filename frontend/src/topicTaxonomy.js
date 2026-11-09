import recommended from './data/topicTaxonomy.json';
export const tagNames = { T1: '业务属性', T2: '经营作用', T3: '内容主题', T4: '目标客群', T5: '使用场景' };
export const tagKey = (tag) => tag.id || tag.client_id || tag.name;
export const isLeaf = (tag) => tag.node_type !== 'group';
export function tagGroups(items, dimension, includeDisabled = false) {
    const values = items[dimension] ?? [];
    const groups = values.filter(item => !isLeaf(item)).map(item => ({ id: tagKey(item), name: item.name, enabled: item.enabled,
        tags: values.filter(tag => isLeaf(tag) && tag.parent_id === tagKey(item) && (includeDisabled || tag.enabled)) }));
    const unassigned = values.filter(tag => isLeaf(tag) && !groups.some(group => group.id === tag.parent_id) && (includeDisabled || tag.enabled));
    if (unassigned.length)
        groups.push({ id: 'unassigned', name: '待归类', enabled: true, tags: unassigned });
    // Migration leftovers are retained for historical references, not current configuration.
    return groups.filter(group => group.name !== '待归类' && (includeDisabled || group.enabled));
}
export function newTaxonomyItem(name, nodeType, parentId = null) {
    const key = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    return { id: null, client_id: `draft-${key}`, name, node_type: nodeType, parent_id: parentId, enabled: true };
}
export function recommendedTaxonomy() {
    const items = {
        T1: ['非营销', '营销'].map(name => newTaxonomyItem(name, 'tag')),
        T2: ['流量', '转化'].map(name => newTaxonomyItem(name, 'tag')),
    };
    for (const dimension of ['T3', 'T4', 'T5']) {
        items[dimension] = [];
        for (const category of recommended[dimension]) {
            const group = newTaxonomyItem(category.name, 'group');
            items[dimension].push(group, ...category.tags.map(name => newTaxonomyItem(name, 'tag', tagKey(group))));
        }
    }
    return items;
}
function object(value) { return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
function text(value) {
    if (typeof value === 'string')
        return value;
    const item = object(value);
    return typeof item.description === 'string' ? item.description : typeof item.name === 'string' ? item.name : '';
}
function first(value) { return Array.isArray(value) ? value[0] : value; }
export function topicLabels(topic, items = {}) {
    const labels = object(topic.labels);
    const get = (dimension) => labels[dimension.toLowerCase()] ?? labels[dimension];
    const nodes = (raw, dimension) => {
        const values = raw == null ? [] : Array.isArray(raw) ? raw : [raw];
        return values.flatMap(value => {
            const entry = object(value);
            const name = text(value);
            if (!name && typeof entry.id !== 'string')
                return [];
            const group = tagGroups(items, dimension, true).find(group => group.tags.some(tag => (entry.id && tag.id === entry.id) || (!entry.id && tag.name === name)));
            const leaf = group?.tags.find(tag => (entry.id && tag.id === entry.id) || (!entry.id && tag.name === name));
            const ownPath = Array.isArray(entry.path_names) ? entry.path_names.filter((part) => typeof part === 'string') : [];
            return [{ id: typeof entry.id === 'string' ? entry.id : leaf ? tagKey(leaf) : name,
                    name: name || leaf?.name || String(entry.id), path: ownPath.length ? ownPath : group && group.id !== 'unassigned' ? [group.name, name || leaf?.name || ''] : [name] }];
        });
    };
    const t1 = first(get('T1'));
    const business = object(t1).business_attribute;
    const scope = object(object(t1).scope);
    const rawScope = [scope.region_names ?? scope.region_codes, scope.organization_names ?? scope.organization_codes]
        .flatMap(value => Array.isArray(value) ? value : []);
    const legacyRegions = topic.applicable_cities;
    const t3 = get('T3');
    const primary = nodes(object(t3).primary ?? first(t3), 'T3')[0] ?? null;
    return {
        business: business === 'marketing' ? '营销' : business === 'non_marketing' ? '非营销' : text(t1) || (topic.is_marketing ? '营销' : '非营销'),
        scope: scope.type === 'national' ? '全国' : rawScope.length ? rawScope.join('、') : legacyRegions?.join('、') || '',
        role: { traffic: '流量', conversion: '转化' }[text(first(get('T2')))] || text(first(get('T2'))),
        primary, related: nodes(object(t3).related, 'T3'), audience: nodes(get('T4'), 'T4'), scenes: nodes(get('T5'), 'T5'), need: text(first(get('T6'))),
    };
}
export const emptyLabelFilters = () => ({ T3: [], T4: [], T5: [] });
export function matchesLabelFilters(topic, filters, items) {
    const labels = topicLabels(topic, items);
    const dimensions = { T3: [labels.primary, ...labels.related].filter((node) => !!node), T4: labels.audience, T5: labels.scenes };
    return ['T3', 'T4', 'T5'].every(dimension => !filters[dimension].length || filters[dimension].some(id => {
        const nodes = dimensions[dimension];
        if (!id.startsWith('group:'))
            return nodes.some(node => node.id === id);
        const group = tagGroups(items, dimension).find(group => group.id === id.slice(6));
        return !!group && nodes.some(node => group.tags.some(tag => tagKey(tag) === node.id));
    }));
}
