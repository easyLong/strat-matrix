import type { ProductionLeadDays } from '../types'

export const productionTopicTypes = [
  { key: 'ordinary', label: '普通选题' },
  { key: 'marketing', label: '营销选题' },
  { key: 'hotspot', label: '热点选题' },
] as const

export function productionTimingValid(value?: ProductionLeadDays | null): boolean {
  return Object.entries(value || {}).every(([key, days]) =>
    productionTopicTypes.some(type => type.key === key) &&
    (days == null || Number.isInteger(days) && days >= 0 && days <= 365))
}

export function productionLeadLabel(days?: number | null): string {
  return days == null ? '未配置' : days === 0 ? 'T−0（投放当天）' : `T−${days}（提前 ${days} 天）`
}
