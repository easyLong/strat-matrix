import { lifecycleGroups, setLifecycleGroups } from './lifecycleRules';
/** Pair AND constraints in one group, never across an OR boundary. */
export function lifecycleRangeRows(group) {
    const rows = [];
    group.forEach((condition, index) => {
        const side = condition.operator === 'eq' ? 'exact' : ['gt', 'gte'].includes(condition.operator) ? 'lower' : 'upper';
        const row = side === 'exact' ? undefined : rows.find(item => item.field === condition.field && item.exact === undefined && item[side] === undefined);
        if (row)
            row[side] = index;
        else
            rows.push({ field: condition.field, [side]: index });
    });
    return rows;
}
export function updateLifecycleBound(rule, groupIndex, row, side, raw) {
    const groups = lifecycleGroups(rule);
    const group = groups[groupIndex];
    const index = row[side];
    if (raw === '') {
        if (index === undefined)
            return;
        const other = side === 'lower' ? row.upper : row.lower;
        // An empty last bound stays invalid until edited or explicitly deleted.
        if (other === undefined)
            group[index].value = Number.NaN;
        else
            group.splice(index, 1);
    }
    else if (index !== undefined)
        group[index].value = Number(raw);
    else
        group.push({ field: row.field, operator: side === 'lower' ? 'gte' : side === 'upper' ? 'lte' : 'eq', value: Number(raw), join: 'AND' });
    setLifecycleGroups(rule, groups);
}
export function updateLifecycleRangeField(rule, groupIndex, row, field) {
    const groups = lifecycleGroups(rule);
    for (const index of [row.lower, row.upper, row.exact])
        if (index !== undefined)
            groups[groupIndex][index].field = field;
    setLifecycleGroups(rule, groups);
}
export function removeLifecycleRange(rule, groupIndex, row) {
    const indices = [row.lower, row.upper, row.exact].filter((item) => item !== undefined);
    if (rule.conditions.length === indices.length)
        return;
    const groups = lifecycleGroups(rule);
    groups[groupIndex] = groups[groupIndex].filter((_, index) => !indices.includes(index));
    setLifecycleGroups(rule, groups.filter(group => group.length));
}
export function lifecycleRangeValid(group, row) {
    const constraints = [row.lower, row.upper, row.exact].filter((item) => item !== undefined).map(index => group[index]);
    if (constraints.some(item => !Number.isInteger(item.value) || item.value < 0))
        return false;
    if (row.lower === undefined || row.upper === undefined)
        return true;
    const lower = group[row.lower], upper = group[row.upper];
    const minimum = lower.value + (lower.operator === 'gt' ? 1 : 0);
    const maximum = upper.value - (upper.operator === 'lt' ? 1 : 0);
    return minimum <= maximum;
}
export const lifecycleRangesValid = (rules) => rules.every(rule => rule.catchAll || lifecycleGroups(rule).every(group => lifecycleRangeRows(group).every(row => lifecycleRangeValid(group, row))));
