/** Only the latest query owned by an active page may update its list. */
export function createAsyncPage(page, fetchPage, fields, reportError) {
  let requestVersion = 0
  let controller
  let disposed = false
  let paused = false
  async function load() {
    if (paused || disposed) return false
    const version = ++requestVersion
    controller?.abort()
    controller = new AbortController()
    page[fields.loading] = true
    try {
      const response = await fetchPage(controller.signal)
      if (disposed || version !== requestVersion) return false
      page[fields.items] = response.items
      page[fields.total] = response.total
      return true
    } catch (error) {
      if (!disposed && version === requestVersion) {
        reportError(error instanceof Error ? error.message : '读取列表失败')
      }
      return false
    } finally {
      if (version === requestVersion) page[fields.loading] = false
    }
  }
  const pause = () => {
    paused = true
    requestVersion++
    controller?.abort()
    page[fields.loading] = false
  }
  page.$on('hook:deactivated', pause)
  page.$on('hook:activated', () => {
    const resumed = paused
    paused = false
    if (resumed) void load()
  })
  page.$once('hook:beforeDestroy', () => { disposed = true; pause() })
  return { load }
}
