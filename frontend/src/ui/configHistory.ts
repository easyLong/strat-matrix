import type { ConfigVersionSummary, StrategyConfig } from '../types';
import { lifecycleRuleSummary } from './lifecycleRules';
export function configVersionNumber(version: ConfigVersionSummary, versions: ConfigVersionSummary[]) {
    const index = versions.findIndex(item => item.version === version.version);
    return index < 0 ? version.version : versions.length - index;
}
export function configDetailRows(config: StrategyConfig) {
    const rows: {
        key: string;
        group: string;
        label: string;
        value: string;
    }[] = [
        { key: 'planning_days', group: '策划内容配置', label: '每周策划日', value: config.planning_days.map(day => ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][day - 1] ?? `周${day}`).join('、') },
        { key: 'schedule', group: '策划内容配置', label: '自动策划调度时间', value: `每周${['一', '二', '三', '四', '五', '六', '日'][config.schedule_day - 1]} ${config.schedule_time}` },
        { key: 'marketing_max', group: '策划内容配置', label: '营销内容周上限', value: `${config.marketing_max} 条 / 营销账号 / 周` },
        { key: 'hotspot_ratio', group: '策划内容配置', label: '热点选题占比', value: `${config.hotspot_ratio}%` },
        { key: 'rolling_posts', group: '策划规则配置', label: '滚动统计窗口', value: `${config.rolling_posts} 篇` },
    ];
    for (const stage of config.stage_targets) {
        rows.push({ key: `stage:${stage.name}:traffic`, group: '策划规则配置', label: `${stage.name} · 流量目标`, value: `${stage.traffic}%` });
        rows.push({ key: `stage:${stage.name}:conversion`, group: '策划规则配置', label: `${stage.name} · 转化目标`, value: `${stage.conversion}%` });
    }
    for (const rule of config.lifecycle_rules) {
        rows.push({ key: `lifecycle:${rule.name}`, group: '策划规则配置', label: rule.name, value: lifecycleRuleSummary(rule, config.lifecycle_rules) });
    }
    return rows;
}
