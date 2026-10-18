import { onBeforeUnmount, ref, watch, type Ref } from 'vue'

export function useDebouncedFields<T extends string>(sources: Record<T, Ref<string>>, delay = 300) {
  const read = () => Object.fromEntries(Object.entries<Ref<string>>(sources).map(([key, source]) => [key, source.value])) as Record<T, string>
  const terms = ref(read()) as Ref<Record<T, string>>
  let timer: ReturnType<typeof setTimeout> | undefined
  function flush() {
    if (timer) clearTimeout(timer)
    const next = read()
    if (Object.keys(next).some(key => next[key as T] !== terms.value[key as T])) terms.value = next
  }
  watch(Object.values(sources) as Ref<string>[], () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(flush, delay)
  })
  onBeforeUnmount(() => { if (timer) clearTimeout(timer) })
  return { terms, flush }
}
