export function beijingDate(value = new Date()) {
    const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(value);
    const part = (type) => parts.find(item => item.type === type).value;
    return `${part('year')}-${part('month')}-${part('day')}`;
}
function validityDate(value) {
    if (!value)
        return null;
    if (/^\d{4}-\d{2}-\d{2}$/.test(value))
        return value;
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value)) {
        // Offset-free source dates follow the host contract's Beijing timezone.
        if (!/(Z|[+-]\d{2}:?\d{2})$/i.test(value))
            return value.slice(0, 10);
        const instant = new Date(value);
        if (Number.isFinite(instant.getTime()))
            return beijingDate(instant);
    }
    return '';
}
export function topicValidOn(topic, date) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date))
        return false;
    const start = validityDate(topic.valid_from), end = validityDate(topic.valid_to);
    return start !== '' && end !== '' && (!start || date >= start) && (!end || date <= end);
}
export function topicValidityLabel(topic) {
    return `${validityDate(topic.valid_from) || '不限'} 至 ${validityDate(topic.valid_to) || '不限'}`;
}
export function marketingTopicName(topic) {
    return topic.related_activity || topic.related_product || topic.topic_id;
}
export function manualTopicTooltip(topic) {
    const details = topic.is_marketing ? [
        `关联活动 ID：${topic.related_activity_id || '—'}`,
        `关联活动名称：${topic.related_activity || '—'}`,
        `所属组织：${topic.activity_organization || '—'}`,
        `关联产品：${topic.related_product || '—'}`,
        `产品 ID：${topic.related_product_id || '—'}`,
    ] : [`选题标题：${topic.topic_title}`, `选题大纲：${topic.outline || '—'}`];
    return [`选题 ID：${topic.topic_id}`, ...details,
        `选题二级分类：${topic.content_type || '—'}`,
        `有效期：${topicValidityLabel(topic)}`,
    ].join('\n');
}
