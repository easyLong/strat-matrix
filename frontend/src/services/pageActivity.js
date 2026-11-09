/** Bind work to native Vue 2 lifecycle events, including cached parent pages. */
export function bindPageActivity(page, start, stop) {
  const activity = { active: false }
  const cached = () => {
    for (let current = page; current; current = current.$parent) {
      if (current._inactive) return true
    }
    return false
  }
  const activate = () => {
    if (activity.active || cached()) return
    activity.active = true
    start()
  }
  const deactivate = () => {
    if (!activity.active) return
    activity.active = false
    stop()
  }
  page.$on('hook:mounted', activate)
  page.$on('hook:activated', activate)
  page.$on('hook:deactivated', deactivate)
  page.$once('hook:beforeDestroy', deactivate)
  return activity
}
