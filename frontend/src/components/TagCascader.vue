<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import type { TagGroup } from '../topicTaxonomy'
import { tagKey } from '../topicTaxonomy'

const props = withDefaults(defineProps<{ modelValue: string[]; groups: TagGroup[]; label: string; allowGroups?: boolean; max?: number; disabled?: boolean }>(), { allowGroups: true, max: Infinity, disabled: false })
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()
const id = useId()
const open = ref(false)
const query = ref('')
const activeGroup = ref('')
const anchor = ref<HTMLElement | null>(null)
const popup = ref<HTMLElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const position = ref({ top: '0px', left: '0px', width: '420px' })
const limitMessage = ref('')
const available = computed(() => props.groups.filter(group => group.enabled).map(group => ({ ...group, tags: group.tags.filter(tag => tag.enabled) })))
const matching = computed(() => available.value.map(group => ({ ...group, tags: group.tags.filter(tag => `${group.name} ${tag.name}`.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase())) })).filter(group => group.tags.length || !query.value.trim()))
const current = computed(() => matching.value.find(group => group.id === activeGroup.value) ?? matching.value[0])
const selectionNames = computed(() => props.modelValue.map(value => {
  for (const group of props.groups) {
    if (value === `group:${group.id}`) return `${group.name} / 全部`
    const leaf = group.tags.find(tag => tagKey(tag) === value)
    if (leaf) return `${group.name} / ${leaf.name}`
  }
  return value
}))
function reposition() {
  if (!anchor.value || !popup.value) return
  const rect = anchor.value.getBoundingClientRect()
  const width = Math.min(440, window.innerWidth - 24)
  const height = Math.min(popup.value.offsetHeight, window.innerHeight - 24)
  position.value = { left: `${Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))}px`, width: `${width}px`,
    top: `${Math.max(12, rect.bottom + height + 6 <= window.innerHeight - 12 ? rect.bottom + 6 : rect.top - height - 6)}px` }
}
function close(returnFocus = false) { open.value = false; limitMessage.value = ''; if (returnFocus) anchor.value?.querySelector<HTMLButtonElement>('button')?.focus() }
async function toggle() {
  if (props.disabled) return
  if (open.value) { close(); return }
  open.value = true
  query.value = ''
  await nextTick()
  reposition()
  searchInput.value?.focus({ preventScroll: true })
}
function choose(value: string, group: TagGroup) {
  limitMessage.value = ''
  if (props.modelValue.includes(value)) { emit('update:modelValue', props.modelValue.filter(item => item !== value)); return }
  let next = props.modelValue.filter(item => value.startsWith('group:') ? !group.tags.some(tag => tagKey(tag) === item) : item !== `group:${group.id}`)
  if (next.length >= props.max) { limitMessage.value = `最多选择${props.max}个标签`; return }
  next = [...next, value]
  emit('update:modelValue', next)
  if (props.max === 1) close(true)
}
function outside(event: Event) { if (event.target instanceof Node && !anchor.value?.contains(event.target) && !popup.value?.contains(event.target)) close() }
function escape(event: KeyboardEvent) { if (open.value && event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true) } }
function scroll(event: Event) { if (open.value && event.target instanceof Node && !popup.value?.contains(event.target)) reposition() }
watch(matching, () => { if (!matching.value.some(group => group.id === activeGroup.value)) activeGroup.value = matching.value[0]?.id ?? '' })
watch(() => props.disabled, value => { if (value) close() })
onMounted(() => { document.addEventListener('pointerdown', outside); document.addEventListener('focusin', outside); document.addEventListener('keydown', escape, true); window.addEventListener('resize', reposition); window.addEventListener('scroll', scroll, true) })
onBeforeUnmount(() => { document.removeEventListener('pointerdown', outside); document.removeEventListener('focusin', outside); document.removeEventListener('keydown', escape, true); window.removeEventListener('resize', reposition); window.removeEventListener('scroll', scroll, true) })
</script>

<template>
  <div ref="anchor" class="tag-cascader" :class="{ 'is-open': open, 'has-value': modelValue.length }">
    <button class="cascader-trigger" type="button" :disabled="disabled" :aria-label="label" aria-haspopup="dialog" :aria-controls="id" :aria-expanded="open" :title="selectionNames.join('、')" @click="toggle">
      <span>{{ selectionNames[0] || '全部' }}</span><small v-if="selectionNames.length > 1">+{{ selectionNames.length - 1 }}</small><svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4" /></svg>
    </button>
    <button v-if="modelValue.length && !disabled" class="cascader-clear" type="button" :aria-label="`清空${label}`" @click="emit('update:modelValue', [])">×</button>
    <Teleport to="body">
      <div v-if="open" :id="id" ref="popup" class="cascader-popup" role="dialog" :aria-label="`选择${label}`" :style="position">
        <div class="cascader-search"><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5" /><path d="m13 13 4 4" /></svg><input ref="searchInput" v-model="query" type="search" :aria-label="`搜索${label}`" placeholder="搜索分类或标签" /></div>
        <div v-if="matching.length" class="cascader-columns">
          <div class="cascader-categories" aria-label="一级分类"><button v-for="group in matching" :key="group.id" type="button" :class="{ active: current?.id === group.id }" :aria-pressed="current?.id === group.id" @click="activeGroup = group.id">{{ group.name }}<span>›</span></button></div>
          <div v-if="current" class="cascader-leaves" :aria-label="`${current.name}二级标签`">
            <label v-if="allowGroups && current.id !== 'unassigned'" class="cascader-option cascader-group-option"><input type="checkbox" :checked="modelValue.includes(`group:${current.id}`)" @change="choose(`group:${current.id}`, current)" /><span>全部{{ current.name }}</span></label>
            <label v-for="tag in current.tags" :key="tagKey(tag)" class="cascader-option" :class="{ selected: modelValue.includes(tagKey(tag)) }"><input type="checkbox" :checked="modelValue.includes(tagKey(tag)) || modelValue.includes(`group:${current.id}`)" @change="choose(tagKey(tag), current)" /><span>{{ tag.name }}</span></label>
            <div v-if="!current.tags.length" class="cascader-empty">暂无标签</div>
          </div>
        </div>
        <div v-else class="cascader-empty">没有匹配的标签</div>
        <div class="cascader-footer"><span v-if="limitMessage" class="cascader-error" role="alert">{{ limitMessage }}</span><span v-else>已选 {{ modelValue.length }} 个</span><button class="text-btn" type="button" @click="close(true)">完成</button></div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.tag-cascader{position:relative;width:100%;min-width:0}.cascader-trigger{display:flex;align-items:center;gap:6px;width:100%;height:36px;padding:0 11px;border:1px solid var(--neutral-200);border-radius:6px;background:var(--surface);color:var(--neutral-700);font:inherit;text-align:left;cursor:pointer}.cascader-trigger>span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.cascader-trigger>svg{width:14px;height:14px;fill:none;stroke:var(--neutral-400);stroke-width:1.5}.has-value .cascader-trigger{padding-right:32px}.has-value .cascader-trigger>svg{display:none}.cascader-trigger small{padding:1px 5px;border-radius:4px;background:var(--primary-50);color:var(--primary-600)}.is-open .cascader-trigger,.cascader-trigger:focus-visible{border-color:var(--primary-500);outline:3px solid #2f4be024}.cascader-trigger:disabled{background:var(--neutral-50);cursor:default}.cascader-clear{position:absolute;right:7px;top:7px;width:22px;height:22px;padding:0;border:0;border-radius:4px;background:transparent;color:var(--neutral-400);cursor:pointer}.cascader-clear:hover{background:var(--neutral-100)}.cascader-popup{position:fixed;z-index:140;box-sizing:border-box;overflow:hidden;border:1px solid var(--neutral-200);border-radius:10px;background:var(--surface);box-shadow:0 8px 28px #1018281c;font-size:13px}.cascader-search{display:flex;align-items:center;gap:8px;margin:10px;padding:0 10px;border:1px solid var(--neutral-200);border-radius:6px}.cascader-search svg{flex:none;width:17px;height:17px;fill:none;stroke:var(--neutral-400);stroke-width:1.5}.cascader-search input{min-width:0;width:100%;height:34px;border:0;outline:0;background:transparent;font:inherit;color:var(--neutral-800)}.cascader-columns{display:grid;grid-template-columns:minmax(120px,40%) 1fr;border-top:1px solid var(--neutral-100)}.cascader-categories,.cascader-leaves{height:260px;overflow-y:auto;overscroll-behavior:contain;padding:5px}.cascader-categories{border-right:1px solid var(--neutral-200);background:var(--neutral-50)}.cascader-categories button{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:36px;padding:7px 10px;border:0;border-radius:5px;background:transparent;color:var(--neutral-600);font:inherit;text-align:left;cursor:pointer}.cascader-categories button.active{background:var(--primary-50);color:var(--primary-600);font-weight:500}.cascader-option{display:flex;align-items:center;gap:9px;min-height:36px;box-sizing:border-box;padding:7px 9px;border-radius:5px;cursor:pointer;color:var(--neutral-700)}.cascader-option:hover{background:var(--neutral-50)}.cascader-option.selected{background:var(--primary-50);color:var(--primary-600)}.cascader-option input{flex:none;width:15px;height:15px;accent-color:var(--primary-600)}.cascader-group-option{margin-bottom:4px;border-bottom:1px solid var(--neutral-100);font-weight:500}.cascader-footer{display:flex;align-items:center;justify-content:space-between;padding:9px 14px;border-top:1px solid var(--neutral-200);color:var(--neutral-400);font-size:12px}.cascader-empty{padding:30px 10px;text-align:center;color:var(--neutral-400)}.cascader-error{color:var(--danger,#e5484d)}
</style>
<style scoped>
.cascader-popup{max-height:calc(100vh - 24px)}.cascader-categories,.cascader-leaves{max-height:calc(100vh - 142px)}
</style>
