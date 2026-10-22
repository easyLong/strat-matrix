import type { PlanItem } from '../types'

// The 12 content-agent types defined in the confirmed planning prototype.
export const CONTENT_TYPES = [
  '三公里好物种草',
  '产品权益种草',
  '三公里活动营销',
  '产品营销',
  '通用活动',
  '金融科普',
  '热点解读',
  '属地推荐',
  '一句话讨论',
  '财商教育',
  '客群兴趣内容',
  '人设故事',
] as const

export interface ContentTypeCount {
  name: string
  count: number
  hint: string
}

export function summarizeContentTypes(items: Pick<PlanItem, 'topic_id' | 'content_type'>[]): ContentTypeCount[] {
  const counts = new Map<string, Set<string>>(CONTENT_TYPES.map(name => [name, new Set<string>()]))
  const legacy = new Map<string, Set<string>>()
  const untyped = new Set<string>()
  for (const item of items) {
    const id = item.topic_id?.trim()
    if (!id) continue
    const type = item.content_type?.trim()
    if (!type) { untyped.add(id); continue }
    const current = counts.get(type)
    if (current) current.add(id)
    else {
      const topics = legacy.get(type) ?? new Set<string>()
      topics.add(id)
      legacy.set(type, topics)
    }
  }
  const result: ContentTypeCount[] = CONTENT_TYPES.map(name => ({
    name,
    count: counts.get(name)!.size,
    hint: '同一选题在同一内容类型下只计一次',
  }))
  if (legacy.size) result.push({
    name: '其他',
    count: new Set([...legacy.values()].flatMap(ids => [...ids])).size,
    hint: [...legacy.entries()].map(([name, ids]) => `${name}：${ids.size}`).join('；'),
  })
  if (untyped.size) result.push({ name: '未设置', count: untyped.size, hint: '已确定选题但未填写内容类型' })
  return result
}
