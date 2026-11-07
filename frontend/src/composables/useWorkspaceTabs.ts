import { computed, nextTick, onBeforeUnmount, provide, ref, watch, type InjectionKey } from '../compat/composition'
import { useRoute, useRouter } from '../compat/router'

export const workspacePages = [
  { key: '/config', title: 'AI策划配置', component: 'PlanningConfigPage' },
  { key: '/manual', title: '人工策划', component: 'PlanningManualPage' },
  { key: '/results', title: '策划结果', component: 'PlanningResultsPage' },
]
export interface WorkspaceTab { key: string; title: string; component: string; location: string }
interface CloseGuard { dirty: () => boolean; confirm: () => Promise<boolean> }
export interface WorkspaceContext { registerCloseGuard: (key: string, guard: CloseGuard) => () => void }
export const workspaceKey: InjectionKey<WorkspaceContext> = Symbol('planning-workspace')

/** Development shell only. The bank host owns its own tabs and page cache. */
export function useWorkspaceTabs(enabled: boolean) {
  const route = useRoute(), router = useRouter()
  const tabs = ref<WorkspaceTab[]>([])
  const closing = ref(false)
  const guards = new Map<string, CloseGuard>()
  if (enabled) provide(workspaceKey, {
    registerCloseGuard(key, guard) {
      guards.set(key, guard)
      return () => { if (guards.get(key) === guard) guards.delete(key) }
    },
  })
  watch(() => route.fullPath, location => {
    if (!enabled) return
    const page = workspacePages.find(page => page.key === route.path)
    if (!page) return
    const tab = tabs.value.find(tab => tab.key === page.key)
    if (tab) tab.location = location
    else tabs.value.push({ ...page, location })
  }, { immediate: true })
  onBeforeUnmount(() => guards.clear())

  const locationFor = (key: string) => tabs.value.find(tab => tab.key === key)?.location || key
  async function select(key: string) {
    if (!closing.value) await router.push(locationFor(key))
  }
  async function close(key: string) {
    if (closing.value) return
    const tab = tabs.value.find(tab => tab.key === key)
    if (!tab) return
    closing.value = true
    try {
      const guard = guards.get(key)
      if (guard?.dirty()) {
        // A cached editor must become visible before showing its confirmation.
        if (route.path !== key) {
          await router.push(tab.location)
          await nextTick()
          if (route.path !== key) return
        }
        if (!await guard.confirm()) return
      }
      if (route.path === key) {
        const index = tabs.value.indexOf(tab)
        const fallback = tabs.value[index - 1] || tabs.value[index + 1]
        await router.replace(fallback?.location || '/workspace')
        if (route.path === key) return
      }
      // Updating include evicts the closed page from Vue's keep-alive cache.
      tabs.value = tabs.value.filter(item => item.key !== key)
    } finally { closing.value = false }
  }
  return { tabs, closing, select, close, locationFor,
    cacheNames: computed(() => tabs.value.map(tab => tab.component)) }
}
