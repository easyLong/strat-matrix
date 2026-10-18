export function statusTone(status: string | null | undefined): string {
  const text = status?.trim() ?? ''
  if (!text || ['状态未知', '未知', '无数据', '未接入', '—', '?', '停用'].includes(text)) return 'gray'
  if (/失败|异常|错误|不通过/.test(text)) return 'red'
  if (/生产中|生成中|上传中/.test(text)) return 'blue'
  if (/进行中|执行中|处理中|待|未提交/.test(text)) return 'orange'
  if (/完成|成功|已生成|已发布|启用|已连接/.test(text)) return 'green'
  if (text === '已规划') return 'blue'
  return 'gray'
}
