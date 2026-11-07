<script lang="ts">
import { defineComponent, nextTick, ref, watch, type PropType } from '../compat/composition'
import type { WorkspaceTab } from '../composables/useWorkspaceTabs'
export default defineComponent({
  props: { tabs: { type: Array as PropType<WorkspaceTab[]>, required: true }, active: String, busy: Boolean },
  setup(props, { emit }) {
    const strip = ref<HTMLElement | null>(null)
    watch(() => props.active, async () => {
      await nextTick()
      strip.value?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    })
    function move(event: KeyboardEvent, index: number) {
      const size = props.tabs.length
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? size - 1
        : event.key === 'ArrowRight' ? (index + 1) % size : event.key === 'ArrowLeft' ? (index + size - 1) % size : -1
      if (next < 0 || props.busy) return
      event.preventDefault()
      emit('select', props.tabs[next].key)
      ;(strip.value?.querySelectorAll('[role="tab"]')[next] as HTMLElement)?.focus()
    }
    return { strip, move }
  },
})
</script>
<template>
  <div ref="strip" class="workspace-tabs" role="tablist" aria-label="业务页面">
    <div v-for="(tab,index) in tabs" :key="tab.key" class="workspace-tab" :class="{ active:active===tab.key }" role="presentation">
      <button class="workspace-tab-select" type="button" role="tab" :aria-selected="active===tab.key" aria-controls="workspace-page" :tabindex="active===tab.key ? 0 : -1" :disabled="busy" @click="$emit('select',tab.key)" @keydown="move($event,index)">{{ tab.title }}</button>
      <button class="workspace-tab-close" type="button" :aria-label="`关闭${tab.title}页签`" :disabled="busy" @click="$emit('close',tab.key)">×</button>
    </div>
  </div>
</template>
<style scoped>
.workspace-tabs{display:flex;align-items:end;gap:6px;min-width:0;width:100%;height:100%;overflow-x:auto;scrollbar-width:thin}
.workspace-tab{display:flex;align-items:center;flex:none;min-height:40px;border:1px solid transparent;border-bottom:0;border-radius:12px 12px 0 0;background:var(--neutral-100);color:var(--text-secondary)}
.workspace-tab.active{border-color:var(--neutral-200);background:var(--surface);color:var(--primary-600);box-shadow:inset 0 -2px var(--primary-600)}
.workspace-tab button{border:0;background:transparent;color:inherit;font:inherit;font-size:14px;cursor:pointer}
.workspace-tab-select{padding:10px 8px 10px 16px;white-space:nowrap}
.workspace-tab-close{display:grid;place-items:center;width:24px;height:24px;padding:0;margin-right:8px;font-size:19px!important;color:var(--text-muted)!important}
.workspace-tab-close:hover{color:var(--danger)!important;background:var(--danger-bg)}
.workspace-tab button:focus-visible{outline:2px solid var(--primary-600);outline-offset:-2px}
</style>
