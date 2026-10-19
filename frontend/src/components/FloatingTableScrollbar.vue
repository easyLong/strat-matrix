<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ target: HTMLElement | null; hidden?: boolean }>(), { hidden: false })
const rail = ref<HTMLElement | null>(null)
const visible = ref(false)
const contentWidth = ref(0)
const position = ref({ left: '0px', width: '0px' })
let measureFrame = 0

function syncFromTable() {
  const table = props.target
  const scrollbar = rail.value
  if (!table || !scrollbar) return
  const tableRange = table.scrollWidth - table.clientWidth
  const railRange = scrollbar.scrollWidth - scrollbar.clientWidth
  const left = tableRange > 0 ? table.scrollLeft / tableRange * railRange : 0
  if (Math.abs(scrollbar.scrollLeft - left) > .5) scrollbar.scrollLeft = left
}

function syncToTable() {
  const table = props.target
  const scrollbar = rail.value
  if (!table || !scrollbar) return
  const railRange = scrollbar.scrollWidth - scrollbar.clientWidth
  const tableRange = table.scrollWidth - table.clientWidth
  const left = railRange > 0 ? scrollbar.scrollLeft / railRange * tableRange : 0
  if (Math.abs(table.scrollLeft - left) > .5) table.scrollLeft = left
}

function measure() {
  const table = props.target
  if (!table?.isConnected) { visible.value = false; return }
  const rect = table.getBoundingClientRect()
  const left = Math.max(0, rect.left)
  const width = Math.max(0, Math.min(rect.right, document.documentElement.clientWidth) - left)
  position.value = { left: `${left}px`, width: `${width}px` }
  contentWidth.value = table.scrollWidth
  visible.value = width > 0 && table.scrollWidth > table.clientWidth + 1
  void nextTick(syncFromTable)
}

function scheduleMeasure() {
  cancelAnimationFrame(measureFrame)
  measureFrame = requestAnimationFrame(measure)
}

function viewportScroll(event: Event) {
  if (event.target !== props.target && event.target !== rail.value) scheduleMeasure()
}

watch(() => props.target, (table, _, cleanup) => {
  if (!table) { visible.value = false; return }
  const observer = new ResizeObserver(scheduleMeasure)
  observer.observe(table)
  if (table.firstElementChild) observer.observe(table.firstElementChild)
  table.addEventListener('scroll', syncFromTable, { passive: true })
  cleanup(() => { observer.disconnect(); table.removeEventListener('scroll', syncFromTable) })
  scheduleMeasure()
}, { immediate: true, flush: 'post' })
watch(rail, () => { void nextTick(syncFromTable) }, { flush: 'post' })

onMounted(() => {
  window.addEventListener('resize', scheduleMeasure)
  window.addEventListener('scroll', viewportScroll, { capture: true, passive: true })
})
onBeforeUnmount(() => {
  cancelAnimationFrame(measureFrame)
  window.removeEventListener('resize', scheduleMeasure)
  window.removeEventListener('scroll', viewportScroll, true)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="visible && !hidden" class="floating-table-scrollbar" :style="position">
      <div ref="rail" class="floating-table-scrollbar-rail" tabindex="0" role="region" aria-label="账号列表横向滚动条" @scroll="syncToTable">
        <div class="floating-table-scrollbar-spacer" :style="{ width: `${contentWidth}px` }" />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.floating-table-scrollbar{position:fixed;z-index:36;bottom:0;box-sizing:border-box;padding:8px 0 calc(8px + env(safe-area-inset-bottom));border-top:1px solid var(--neutral-200);border-radius:8px 8px 0 0;background:var(--surface);box-shadow:0 -4px 14px #1018280a}
.floating-table-scrollbar-rail{height:16px;overflow-x:scroll;overflow-y:hidden;overscroll-behavior-x:contain;scrollbar-width:auto;scrollbar-color:var(--neutral-400) var(--neutral-100)}
.floating-table-scrollbar-rail:focus-visible{outline:2px solid var(--primary-300);outline-offset:2px;border-radius:4px}
.floating-table-scrollbar-rail::-webkit-scrollbar{height:12px}
.floating-table-scrollbar-rail::-webkit-scrollbar-track{border-radius:8px;background:var(--neutral-100)}
.floating-table-scrollbar-rail::-webkit-scrollbar-thumb{min-width:48px;border:2px solid var(--neutral-100);border-radius:8px;background:var(--neutral-400)}
.floating-table-scrollbar-rail::-webkit-scrollbar-thumb:hover{background:var(--neutral-500)}
.floating-table-scrollbar-spacer{height:1px}
</style>
