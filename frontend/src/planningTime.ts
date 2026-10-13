/** Calendar calculations use the project's business timezone, Asia/Shanghai. */
const DAY = 86400000
const SHANGHAI_OFFSET = 8 * 3600000

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
