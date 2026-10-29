<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'

const props = withDefaults(defineProps<{ text: string; showIcon?: boolean; overflowOnly?: boolean }>(), {
  showIcon: true,
  overflowOnly: false,
})
defineOptions({ inheritAttrs: false })

const tooltipId = useId()
const trigger = ref<HTMLButtonElement | null>(null)
const tooltip = ref<HTMLElement | null>(null)
const open = ref(false)
const position = ref({ left: '0px', top: '0px', visibility: 'hidden' as 'hidden' | 'visible' })
let closeTimer: ReturnType<typeof setTimeout> | undefined
const hovered = ref(false)
const focused = ref(false)

function close() {
  clearTimeout(closeTimer)
  open.value = false
}

function place() {
  if (!open.value || !trigger.value || !tooltip.value) return
  const anchor = trigger.value.getBoundingClientRect()
  const box = tooltip.value.getBoundingClientRect()
  const left = Math.max(12, Math.min(anchor.left, window.innerWidth - box.width - 12))
  const below = anchor.bottom + 8
  const top = below + box.height <= window.innerHeight - 12 ? below : Math.max(12, anchor.top - box.height - 8)
  position.value = { left: `${left}px`, top: `${top}px`, visibility: 'visible' }
}

async function show() {
  if (props.overflowOnly) {
    const content = trigger.value?.firstElementChild
    if (!content || content.scrollWidth <= content.clientWidth) { close(); return }
  }
  clearTimeout(closeTimer)
  if (!open.value) position.value.visibility = 'hidden'
  open.value = true
  await nextTick()
  place()
}

function scheduleClose() {
  clearTimeout(closeTimer)
  closeTimer = setTimeout(() => {
    if (!hovered.value && !focused.value) close()
  }, 120)
}

function dismissOutside(event: PointerEvent) {
  const target = event.target as Node | null
  if (target && !trigger.value?.contains(target) && !tooltip.value?.contains(target)) close()
}

function dismissEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') close()
}

onMounted(() => {
  document.addEventListener('pointerdown', dismissOutside)
  document.addEventListener('keydown', dismissEscape)
  window.addEventListener('resize', place)
  window.addEventListener('scroll', place, true)
})
onBeforeUnmount(() => {
  clearTimeout(closeTimer)
  document.removeEventListener('pointerdown', dismissOutside)
  document.removeEventListener('keydown', dismissEscape)
  window.removeEventListener('resize', place)
  window.removeEventListener('scroll', place, true)
})
</script>

<template>
  <button ref="trigger" v-bind="$attrs" type="button" class="hover-hint" :aria-describedby="open ? tooltipId : undefined"
    @mouseenter="hovered = true; show()" @mouseleave="hovered = false; scheduleClose()"
    @focus="focused = true; show()" @blur="focused = false; scheduleClose()" @click="show">
    <slot />
    <span v-if="showIcon" class="field-help-tip" aria-hidden="true">?</span>
  </button>
  <Teleport to="body">
    <div v-if="open" :id="tooltipId" ref="tooltip" class="hover-hint-tooltip" :style="position" role="tooltip"
      @mouseenter="hovered = true; show()" @mouseleave="hovered = false; scheduleClose()">{{ text }}</div>
  </Teleport>
</template>

<style scoped>
.hover-hint{display:inline-flex;align-items:center;gap:6px;padding:0;border:0;background:transparent;color:var(--neutral-500);font:inherit;font-size:13px;white-space:nowrap;cursor:help}
.hover-hint:hover,.hover-hint:focus-visible{color:var(--primary-600)}
.hover-hint:focus-visible{outline:2px solid var(--primary-600);outline-offset:3px;border-radius:4px}
.hover-hint .field-help-tip{flex-shrink:0;color:inherit}
.hover-hint-tooltip{position:fixed;z-index:1200;box-sizing:border-box;width:max-content;max-width:min(320px,calc(100vw - 24px));padding:10px 12px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface);box-shadow:var(--shadow-3);color:var(--neutral-700);font-size:13px;line-height:20px;white-space:normal;overflow-wrap:anywhere}
</style>

<style scoped>
.hover-hint-tooltip{max-height:min(360px,calc(100vh - 24px));overflow-y:auto;overscroll-behavior:contain;white-space:pre-wrap}
</style>
