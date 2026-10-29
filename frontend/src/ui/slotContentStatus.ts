import type { PlanItem } from '../types'

export type SlotContentStatus = '待定题' | '待生产' | '生产中' | '已完成' | '生产失败'

const statusLabels: Record<string, SlotContentStatus> = {
  planned: '待生产',
  ready: '生产中',
  generated: '已完成',
  published: '已完成',
  failed: '生产失败',
  '待生产': '待生产',
  '待生成': '待生产',
  '未生成': '待生产',
  '生成中': '生产中',
  '生产中': '生产中',
  '上传中': '生产中',
  '已完成': '已完成',
  '已生成': '已完成',
  '生成完成': '已完成',
  '生产完成': '已完成',
  '已发布': '已完成',
  '生成失败': '生产失败',
  '生产失败': '生产失败',
  '生产异常': '生产失败',
}

export function productionStatusLabel(
  item: Pick<PlanItem, 'topic_id' | 'topic_type' | 'slot_type' | 'production_status' | 'status'>,
): SlotContentStatus {
  if (!item.topic_id?.trim()) {
    const hotspot = item.slot_type === 'hotspot' || item.topic_type === '热点' || item.topic_type === 'hotspot'
    return hotspot ? '待定题' : '待生产'
  }
  return statusLabels[item.production_status ?? ''] ?? statusLabels[item.status] ?? '待生产'
}

export function canReplacePlanTopic(item: PlanItem): boolean {
  return item.allow_replace && Boolean(item.topic_id?.trim())
    && !['生产中', '已完成'].includes(productionStatusLabel(item))
}
