/** Calendar calculations use the project's business timezone, Asia/Shanghai. */
const DAY = 86400000
const SHANGHAI_OFFSET = 8 * 3600000

/** Display timestamps to seconds; timestamps without an offset are business wall time. */
export function formatDateTime(value: string | null | undefined): string {
  const text = value?.trim()
  if (!text) return '\u2014'
  const parts = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::(\d{2}))?(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?$/i.exec(text)
  if (!parts) return text
  if (parts[4]) {
    const instant = Date.parse(text.replace(' ', 'T'))
    if (!Number.isFinite(instant)) return text
    return new Date(instant + SHANGHAI_OFFSET).toISOString().slice(0, 19).replace('T', ' ')
  }
  return `${parts[1]} ${parts[2]}:${parts[3] ?? '00'}`
}

export function businessMonday(instant: number): string {
  const local = new Date(instant + SHANGHAI_OFFSET)
  local.setUTCDate(local.getUTCDate() - (local.getUTCDay() + 6) % 7)
  return local.toISOString().slice(0, 10)
}

export function addCalendarDays(day: string, count: number): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) + count * DAY).toISOString().slice(0, 10)
}

export function weeklyTrigger(monday: string, weekday: number, time: string): number {
  const [hour, minute] = time.split(':').map(Number)
  return Date.parse(`${monday}T00:00:00Z`) + (weekday - 1) * DAY
    + (hour * 60 + minute) * 60000 - SHANGHAI_OFFSET
}

export function formatBusinessTime(instant: number): string {
  const local = new Date(instant + SHANGHAI_OFFSET)
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  return `${local.toISOString().slice(0, 10)} ${weekdays[local.getUTCDay()]} ${local.toISOString().slice(11, 16)}`
}
