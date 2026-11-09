import { lifecycleRuleSummary } from './lifecycleRules';
import { productionLeadLabel, productionTopicTypes } from './productionTiming';
export function configValuesEqual(left, right) {
    function canonical(value) {
        if (Array.isArray(value))
            return value.map(canonical);
        if (value !== null && typeof value === 'object') {
            const values = value;
            return Object.fromEntries(Object.keys(values).sort().filter(key => values[key] !== undefined)
                .map(key => [key, canonical(values[key])]));
        }
        return value;
    }
    return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
}
export function configVersionNumber(version, versions) {
    const index = versions.findIndex(item => item.version === version.version);
    return index < 0 ? version.version : versions.length - index;
}
export function configHistorySummary(config) {
    return [
        `每周 ${Array.isArray(config.planning_days) ? `${config.planning_days.length} 天` : '未记录'}`,
        `营销上限 ${config.marketing_max ?? '未记录'}`,
        `滚动 ${config.rolling_posts == null ? '未记录' : `${config.rolling_posts} 篇`}`,
        ...(config.lifecycle_rules?.length ? ['五阶段目标与定义'] : []),
    ].join(' · ');
}
export function canRestoreConfig(config) {
    return Array.isArray(config.planning_days) && config.planning_days.length > 0 &&
        config.schedule_day != null && config.schedule_time != null &&
        config.marketing_max != null && config.hotspot_ratio != null && config.rolling_posts != null &&
        config.stage_targets?.length === 5 && config.lifecycle_rules?.length === 5;
}
export function configDetailRows(config) {
    const rows = [
        { key: 'planning_days', group: '策划内容配置', label: '每周策划日', value: config.planning_days?.map(day => ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][day - 1] ?? `周${day}`).join('、') || '未记录' },
        { key: 'schedule', group: '策划内容配置', label: '自动策划调度时间', value: config.schedule_day != null && config.schedule_time != null ? `每周${['一', '二', '三', '四', '五', '六', '日'][config.schedule_day - 1]} ${config.schedule_time}` : '未记录' },
        { key: 'marketing_max', group: '策划内容配置', label: '营销内容周上限', value: config.marketing_max == null ? '未记录' : `${config.marketing_max} 条 / 营销账号 / 周` },
        { key: 'hotspot_ratio', group: '策划内容配置', label: '热点选题占比', value: config.hotspot_ratio == null ? '未记录' : `${config.hotspot_ratio}%` },
        ...productionTopicTypes.map(type => ({ key: `production:${type.key}`, group: '策划内容配置', label: `${type.label} · 内容生产时间`, value: config.content_production_lead_days == null ? '未记录' : productionLeadLabel(config.content_production_lead_days[type.key]) })),
        { key: 'rolling_posts', group: '策划规则配置', label: '滚动统计窗口', value: config.rolling_posts == null ? '未记录' : `${config.rolling_posts} 篇` },
    ];
    for (const stage of config.stage_targets ?? []) {
        rows.push({ key: `stage:${stage.name}:traffic`, group: '策划规则配置', label: `${stage.name} · 流量目标`, value: `${stage.traffic}%` });
        rows.push({ key: `stage:${stage.name}:conversion`, group: '策划规则配置', label: `${stage.name} · 转化目标`, value: `${stage.conversion}%` });
    }
    for (const rule of config.lifecycle_rules ?? []) {
        rows.push({ key: `lifecycle:${rule.name}`, group: '策划规则配置', label: rule.name, value: lifecycleRuleSummary(rule, config.lifecycle_rules ?? []) });
    }
    return rows;
}
