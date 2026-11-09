export function weekStart(value) {
    const date = new Date(`${value}T00:00:00Z`);
    date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7);
    return date.toISOString().slice(0, 10);
}
export function weekEnd(value) {
    const date = new Date(`${weekStart(value)}T00:00:00Z`);
    date.setUTCDate(date.getUTCDate() + 6);
    return date.toISOString().slice(0, 10);
}
export function cyclePeriodLabel(value) {
    if (!value)
        return '全部周期';
    const date = new Date(`${weekStart(value)}T00:00:00Z`);
    return `${date.getUTCFullYear()}年${date.getUTCMonth() + 1}月第${Math.floor((date.getUTCDate() - 1) / 7) + 1}周`;
}
export function topicTypeLabel(item) {
    if (!item.topic_id)
        return '待确定';
    const type = String(item.topic_type ?? '');
    if (type === '营销' || type === 'marketing' || type === 'marketing_priority')
        return '营销';
    if (type === '热点' || type === 'hotspot')
        return '热点';
    return '普通';
}
export function weekdayLabel(date) {
    return new Intl.DateTimeFormat('zh-CN', { weekday: 'short', timeZone: 'UTC' }).format(new Date(`${date}T00:00:00Z`));
}
export function sourceLabel(item) {
    return item.plan_type === 'manual' ? '人' : 'AI';
}
export function sourceHint(item) {
    return item.plan_type === 'manual' ? '人：人工策划' : 'AI：自动策划';
}
export function daysFor(week) {
    const start = new Date(`${week.start}T00:00:00Z`);
    return Array.from({ length: 7 }, (_, offset) => {
        const date = new Date(start);
        date.setUTCDate(start.getUTCDate() + offset);
        const value = date.toISOString().slice(0, 10);
        return {
            date: value,
            label: value.slice(5),
            weekday: weekdayLabel(value),
            items: week.items.filter(item => item.publish_date === value),
        };
    });
}
