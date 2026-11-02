import type { LifecycleRule, LifecycleCondition } from '../types';
export const lifecycleMetricOptions = [
    { value: 'valid_content_count', label: '有效内容数', unit: '篇' },
    { value: 'rolling_interaction_count', label: '滚动篇均互动数', unit: '次/篇' },
    { value: 'followers_count', label: '粉丝数', unit: '人' },
];
export const lifecycleOperatorOptions = [
    { value: 'lt', label: '<' },
    { value: 'lte', label: '≤' },
    { value: 'gte', label: '≥' },
    { value: 'gt', label: '>' },
    { value: 'eq', label: '=' },
];
export function metricUnit(field: string) {
    return lifecycleMetricOptions.find(option => option.value === field)?.unit ?? '';
}
export function coldStartSummary(rules: LifecycleRule[]) {
    const growth = rules.find(rule => rule.name === '流量增长期');
    const lowBoundary = growth?.conditions.filter(condition => ['followers_count', 'valid_content_count'].includes(condition.field) && condition.operator === 'gte') ?? [];
    if (!lowBoundary.length)
        return '未命中其他阶段时归入此阶段';
    const conditions = lowBoundary.map(condition => {
        const metric = lifecycleMetricOptions.find(option => option.value === condition.field);
        return `${metric?.label ?? condition.field} < ${condition.value} ${metric?.unit ?? ''}`;
    });
    return `${conditions.join(' 或 ')}；未命中其他阶段时也归入此阶段`;
}
export function lifecycleRuleSummary(rule: LifecycleRule, rules: LifecycleRule[]) {
    if (rule.catchAll)
        return coldStartSummary(rules);
    if (rule.condition_mode === 'grouped')
        return lifecycleGroups(rule).map(group => group.map(condition => {
            const metric = lifecycleMetricOptions.find(option => option.value === condition.field);
            const operator = lifecycleOperatorOptions.find(option => option.value === condition.operator);
            return `${metric?.label ?? condition.field} ${operator?.label ?? condition.operator} ${condition.value} ${metric?.unit ?? ''}`;
        }).join(' 且 ')).map(group => `（${group}）`).join(' 或 ');
    return rule.conditions.map((condition, index) => {
        const metric = lifecycleMetricOptions.find(option => option.value === condition.field);
        const operator = lifecycleOperatorOptions.find(option => option.value === condition.operator);
        const prefix = index === 0 ? '' : condition.join === 'OR' ? ' 或 ' : ' 且 ';
        return `${prefix}${metric?.label ?? condition.field} ${operator?.label ?? condition.operator} ${condition.value} ${metric?.unit ?? ''}`;
    }).join('');
}
export function lifecycleGroups(rule: LifecycleRule): LifecycleCondition[][] {
    const groups: LifecycleCondition[][] = [];
    for (const condition of rule.conditions) {
        if (!groups.length || condition.join === 'OR')
            groups.push([]);
        groups[groups.length - 1]!.push(condition);
    }
    return groups;
}
export function setLifecycleGroups(rule: LifecycleRule, groups: LifecycleCondition[][]) {
    rule.conditions = groups.flatMap((group, groupIndex) => group.map((condition, index) => ({ ...condition, join: groupIndex > 0 && index === 0 ? 'OR' : 'AND' })));
}
export function addLifecycleCondition(rule: LifecycleRule, groupIndex: number) {
    const groups = lifecycleGroups(rule);
    groups[groupIndex]!.push({ field: 'valid_content_count', operator: 'gte', value: 0, join: 'AND' });
    setLifecycleGroups(rule, groups);
}
export function addLifecycleGroup(rule: LifecycleRule) {
    setLifecycleGroups(rule, [...lifecycleGroups(rule), [{ field: 'valid_content_count', operator: 'gte', value: 0, join: 'OR' }]]);
}
export function removeLifecycleCondition(rule: LifecycleRule, groupIndex: number, conditionIndex: number) {
    const groups = lifecycleGroups(rule);
    groups[groupIndex]!.splice(conditionIndex, 1);
    if (!groups[groupIndex]!.length)
        groups.splice(groupIndex, 1);
    if (groups.length)
        setLifecycleGroups(rule, groups);
}
export function normalizeLifecycleRule(rule: LifecycleRule) {
    if (rule.condition_mode !== 'grouped') {
        let groups: LifecycleCondition[][] = [];
        rule.conditions.forEach((condition, index) => {
            if (index === 0 || condition.join === 'OR')
                groups.push([{ ...condition }]);
            else
                groups = groups.map(group => [...group, { ...condition }]);
        });
        setLifecycleGroups(rule, groups);
        rule.condition_mode = 'grouped';
    }
}
