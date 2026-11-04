import { onBeforeUnmount, type Ref } from '../compat/composition'
import type { PageResult } from '../api/queries'

/** Shared request ownership: only the latest query can update a list. */
export function useAsyncPage<T>(
  fetchPage: (signal: AbortSignal) => Promise<PageResult<T>>,
  state: { items: Ref<T[]>; total: Ref<number>; loading: Ref<boolean> },
  reportError: (message: string) => void,
) {
  let requestVersion = 0
  let controller: AbortController | undefined
  let disposed = false
  async function load() {
    const version = ++requestVersion
    controller?.abort()
    controller = new AbortController()
    state.loading.value = true
    try {
      const response = await fetchPage(controller.signal)
      if (disposed || version !== requestVersion) return false
      state.items.value = response.items
      state.total.value = response.total
      return true
    } catch (error) {
      if (!disposed && version === requestVersion) {
        reportError(error instanceof Error ? error.message : '读取列表失败')
      }
      return false
    } finally {
      if (version === requestVersion) state.loading.value = false
    }
  }
  onBeforeUnmount(() => { disposed = true; controller?.abort() })
  return { load }
}
