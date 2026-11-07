import { getCurrentInstance, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from '../compat/composition'

/** Idempotent lifecycle for both normal routes and the host's keep-alive cache. */
export function useActivePage(start: () => void, stop: () => void) {
  // Vue 2 may mount a newly rendered descendant after its keep-alive parent was
  // already deactivated. Its own mounted hook must not start hidden listeners.
  type CachedVm = { _inactive?: boolean | null; $parent?: CachedVm }
  const vm = getCurrentInstance()?.proxy as unknown as CachedVm | undefined
  const cached = () => {
    for (let current = vm; current; current = current.$parent) if (current._inactive) return true
    return false
  }
  const active = ref(false)
  const activate = () => { if (!active.value && !cached()) { active.value = true; start() } }
  const deactivate = () => { if (active.value) { active.value = false; stop() } }
  onMounted(activate)
  onActivated(activate)
  onDeactivated(deactivate)
  onBeforeUnmount(deactivate)
  return active
}
