<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import HoverHint from './HoverHint.vue'
import type { TagTaxonomyItem } from '../api'
import { isLeaf, newTaxonomyItem, tagGroups, tagKey, tagNames, type TaxonomyItems } from '../topicTaxonomy'
const props = withDefaults(defineProps<{ modelValue: TaxonomyItems; editing?: boolean; disabled?: boolean }>(), { editing: false, disabled: false })
const emit = defineEmits<{ 'update:modelValue': [value: TaxonomyItems] }>()
const active = ref('T3')
const collapsed = ref<string[]>([])
const groupInput = ref('')
const leafInputs = ref<Record<string, string>>({})
const selected = ref<string | null>(null)
const renameValue = ref('')
const error = ref('')
const action = ref<'menu' | 'rename'>('menu')
const popover = ref<HTMLElement | null>(null)
const renameInput = ref<HTMLInputElement | null>(null)
const position = ref({ left: '0px', top: '0px' })
let anchor: HTMLElement | null = null
const groups = computed(() => tagGroups(props.modelValue, active.value, true))
const selectedItem = computed(() => (props.modelValue[active.value] ?? []).find(item => tagKey(item) === selected.value))
function commit(items: TagTaxonomyItem[]) { emit('update:modelValue', { ...props.modelValue, [active.value]: items }) }
function validateName(value: string, type: 'tag' | 'group', excluded?: string) {
  if (!value || value.length > 80) { error.value = '名称需为1至80字'; return false }
  if ((props.modelValue[active.value] ?? []).some(item => tagKey(item) !== excluded && (item.node_type ?? 'tag') === type && item.name === value)) {
    error.value = type === 'group' ? '分类名称已存在' : '标签名称已存在'; return false
  }
  error.value = ''; return true
}
function addGroup() {
  if (!props.editing || props.disabled) return
  const name = groupInput.value.trim()
  if (!validateName(name, 'group')) return
  commit([...(props.modelValue[active.value] ?? []), newTaxonomyItem(name, 'group')])
  groupInput.value = ''
}
function addLeaf(groupId: string) {
  if (!props.editing || props.disabled) return
  const name = (leafInputs.value[groupId] ?? '').trim()
  if (!validateName(name, 'tag')) return
  commit([...(props.modelValue[active.value] ?? []), newTaxonomyItem(name, 'tag', groupId === 'unassigned' ? null : groupId)])
  leafInputs.value[groupId] = ''
}
function closeActions(restoreFocus = false) {
  const previousAnchor = anchor
  selected.value = null
  anchor = null
  error.value = ''
  if (restoreFocus && previousAnchor?.isConnected) previousAnchor.focus({ preventScroll: true })
}
function positionActions() {
  if (!anchor?.isConnected || !popover.value) return
  const rect = anchor.getBoundingClientRect()
  if (rect.bottom < 0 || rect.top > window.innerHeight) { closeActions(); return }
  const width = popover.value.offsetWidth
  const height = popover.value.offsetHeight
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))
  const top = rect.bottom + 6 + height <= window.innerHeight - 8
    ? rect.bottom + 6 : Math.max(8, rect.top - height - 6)
  position.value = { left: `${left}px`, top: `${top}px` }
}
async function select(item: TagTaxonomyItem, event: MouseEvent) {
  if (!props.editing || props.disabled) return
  if (selected.value === tagKey(item)) { closeActions(); return }
  anchor = event.currentTarget as HTMLElement
  selected.value = tagKey(item)
  action.value = 'menu'
  renameValue.value = item.name; error.value = ''
  await nextTick()
  positionActions()
  popover.value?.querySelector<HTMLButtonElement>('.taxonomy-menu-item')?.focus({ preventScroll: true })
}
async function editAction(value: 'menu' | 'rename') {
  action.value = value
  error.value = ''
  await nextTick()
  positionActions()
  if (value === 'rename') { renameInput.value?.focus({ preventScroll: true }); renameInput.value?.select() }
  else popover.value?.querySelector<HTMLButtonElement>('.taxonomy-menu-item')?.focus({ preventScroll: true })
}
function saveName() {
  const item = selectedItem.value
  if (!item || !props.editing || props.disabled) return
  if (!validateName(renameValue.value.trim(), item.node_type ?? 'tag', tagKey(item))) return
  commit(props.modelValue[active.value].map(candidate => tagKey(candidate) === tagKey(item) ? { ...candidate, name: renameValue.value.trim() } : candidate))
  closeActions(true)
}
function toggleEnabled() {
  const item = selectedItem.value
  if (!item || !props.editing || props.disabled) return
  const next = props.modelValue[active.value].map(candidate => tagKey(candidate) === tagKey(item) ? { ...candidate, enabled: !candidate.enabled } : candidate)
  if (!tagGroups({ [active.value]: next }, active.value).some(group => group.tags.some(tag => tag.enabled))) { error.value = '请至少保留一个启用分类及标签'; return }
  commit(next); closeActions(true)
}
function toggleGroup(id: string) { closeActions(); collapsed.value = collapsed.value.includes(id) ? collapsed.value.filter(value => value !== id) : [...collapsed.value, id] }
function outsideActions(event: Event) {
  if (!selected.value || !(event.target instanceof Node)) return
  if (!popover.value?.contains(event.target) && !anchor?.contains(event.target)) closeActions()
}
function escapeActions(event: KeyboardEvent) {
  if (selected.value && event.key === 'Escape') { event.preventDefault(); closeActions(true) }
}
watch([active, () => props.editing, () => props.disabled], () => { closeActions(); groupInput.value = ''; leafInputs.value = {} })
watch(selectedItem, item => { if (!item && selected.value) closeActions() })
watch(error, async () => { await nextTick(); positionActions() })
onMounted(() => {
  document.addEventListener('pointerdown', outsideActions)
  document.addEventListener('keydown', escapeActions)
  window.addEventListener('resize', positionActions)
  window.addEventListener('scroll', positionActions, true)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', outsideActions)
  document.removeEventListener('keydown', escapeActions)
  window.removeEventListener('resize', positionActions)
  window.removeEventListener('scroll', positionActions, true)
})
</script>
<template>
  <div class="taxonomy-panel">
    <div class="taxonomy-tabs-row"><div class="taxonomy-tabs" role="tablist" aria-label="标签维度"><button v-for="dimension in ['T1', 'T2', 'T3', 'T4', 'T5']" :key="dimension" type="button" role="tab" :aria-selected="active === dimension" :class="{ active: active === dimension }" @click="active = dimension">{{ dimension }} {{ tagNames[dimension] }}</button></div><HoverHint text="模型生成一条核心需求，可在选题详情查看。">T6 用户需求</HoverHint></div>
    <div v-if="active === 'T1' || active === 'T2'" class="taxonomy-fixed"><span class="taxonomy-fixed-label">{{ active === 'T1' ? '营销属性' : '经营作用' }}</span><div class="taxonomy-pills"><span v-for="item in (modelValue[active] ?? []).filter(isLeaf)" :key="tagKey(item)" class="taxonomy-pill" :class="{ inactive: !item.enabled }">{{ item.name }}</span></div></div>
    <div v-else class="taxonomy-groups" :data-dimension="active">
      <section v-for="group in groups" :key="group.id" class="taxonomy-group" :class="{ inactive: !group.enabled }">
        <div class="taxonomy-group-head"><button class="taxonomy-fold" type="button" :aria-label="`${collapsed.includes(group.id) ? '展开' : '收起'}${group.name}`" :aria-expanded="!collapsed.includes(group.id)" @click="toggleGroup(group.id)"><svg :class="{ folded: collapsed.includes(group.id) }" viewBox="0 0 16 16"><path d="m4 6 4 4 4-4" /></svg></button><button v-if="editing && group.id !== 'unassigned'" class="taxonomy-group-title" type="button" :disabled="disabled" aria-haspopup="dialog" :aria-expanded="selected === group.id" @click="select(modelValue[active].find(item => tagKey(item) === group.id)!, $event)">{{ group.name }}</button><b v-else>{{ group.name }}</b><small v-if="!group.enabled">已停用</small></div>
        <div v-show="!collapsed.includes(group.id)" class="taxonomy-group-body"><div class="taxonomy-pills"><button v-for="tag in group.tags" :key="tagKey(tag)" class="taxonomy-pill" :class="{ inactive: !tag.enabled, selected: selected === tagKey(tag) }" type="button" :disabled="!editing || disabled" :title="`${group.name} / ${tag.name}${!tag.enabled ? ' · 已停用' : ''}`" :aria-haspopup="editing ? 'dialog' : undefined" :aria-expanded="editing ? selected === tagKey(tag) : undefined" @click.stop="select(tag, $event)">{{ tag.name }}</button><span v-if="!group.tags.length && !editing" class="taxonomy-no-tags">暂无标签</span></div><div v-if="editing && group.enabled" class="taxonomy-inline-add"><input v-model="leafInputs[group.id]" type="text" :aria-label="`在${group.name}新增标签`" placeholder="标签名称" maxlength="80" :disabled="disabled" @keydown.enter.prevent="addLeaf(group.id)" /><button type="button" :disabled="disabled || !leafInputs[group.id]?.trim()" @click="addLeaf(group.id)">＋ 添加</button></div></div>
      </section>
      <div v-if="!groups.length && !editing" class="empty-state">暂无标签分类</div>
      <div v-if="editing" class="taxonomy-add-group"><input v-model="groupInput" type="text" aria-label="新增一级分类名称" placeholder="一级分类名称" maxlength="80" :disabled="disabled" @keydown.enter.prevent="addGroup" /><button class="btn" type="button" :disabled="disabled || !groupInput.trim()" @click="addGroup">＋ 添加分类</button></div>
    </div>
    <p v-if="error && !selectedItem" class="inline-error taxonomy-error" role="alert">{{ error }}</p>
  </div>
  <Teleport to="body">
    <section v-if="editing && selectedItem" ref="popover" class="taxonomy-action-popover" :class="{ 'is-form': action !== 'menu' }" :style="position" role="dialog" :aria-label="`${selectedItem.name}操作`">
      <header class="taxonomy-action-head"><b>{{ selectedItem.name }}</b><button class="taxonomy-close" type="button" aria-label="关闭标签操作" @click="closeActions(true)">×</button></header>
      <template v-if="action === 'menu'">
        <button class="taxonomy-menu-item" type="button" :disabled="disabled" @click="editAction('rename')">改名</button>
        <button class="taxonomy-menu-item" :class="{ 'is-danger': selectedItem.enabled }" type="button" :disabled="disabled" @click="toggleEnabled">{{ selectedItem.enabled ? '停用' : '启用' }}</button>
      </template>
      <form v-else @submit.prevent="saveName">
        <label class="taxonomy-action-field"><span>名称</span><input ref="renameInput" v-model="renameValue" aria-label="修改名称" maxlength="80" :disabled="disabled" /></label>
        <div class="taxonomy-action-footer"><button class="btn" type="button" @click="editAction('menu')">返回</button><button class="btn primary" type="submit" :disabled="disabled || !renameValue.trim() || renameValue.trim() === selectedItem.name">确认改名</button></div>
      </form>
      <p v-if="error" class="taxonomy-action-error" role="alert">{{ error }}</p>
    </section>
  </Teleport>
</template>
<style scoped>
.taxonomy-panel{min-width:0}.taxonomy-tabs-row{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid var(--neutral-200);padding:0 18px}.taxonomy-tabs{display:flex;gap:19px;overflow-x:auto}.taxonomy-tabs button{flex:none;padding:13px 0 11px;border:0;border-bottom:2px solid transparent;background:transparent;color:var(--neutral-500);font-size:13px;font-weight:500;white-space:nowrap}.taxonomy-tabs button.active{color:var(--primary-600);border-bottom-color:var(--primary-600)}.taxonomy-tabs-row :deep(.hover-hint){flex:none;font-size:12px;color:var(--neutral-400)}.taxonomy-groups{padding:3px 18px 14px}.taxonomy-group{padding:13px 0;border-bottom:1px solid var(--neutral-100)}.taxonomy-group:last-of-type{border-bottom:0}.taxonomy-group-head{display:flex;align-items:center;gap:6px;margin-bottom:10px;min-height:22px}.taxonomy-group-head>b,.taxonomy-group-title{font-size:13px;font-weight:600;color:var(--neutral-800)}.taxonomy-group-title{padding:0;border:0;background:transparent}.taxonomy-group-title:hover{color:var(--primary-600)}.taxonomy-fold{display:grid;place-items:center;padding:0;width:18px;height:22px;border:0;background:transparent}.taxonomy-fold svg{width:13px;height:13px;fill:none;stroke:var(--neutral-400);stroke-width:1.6;transition:transform .15s}.taxonomy-fold .folded{transform:rotate(-90deg)}.taxonomy-group-head small{color:var(--neutral-400);font-size:11px}.taxonomy-group-body{padding-left:24px}.taxonomy-pills{display:flex;flex-wrap:wrap;gap:7px}.taxonomy-pill{padding:4px 9px;border:1px solid transparent;border-radius:5px;background:var(--primary-50);color:var(--primary-600);font-size:12px;line-height:17px;max-width:100%;overflow-wrap:anywhere}.taxonomy-pill:disabled{opacity:1;cursor:default}.taxonomy-pill:not(:disabled):hover,.taxonomy-pill.selected{border-color:var(--primary-300);background:var(--primary-100)}[data-dimension="T4"] .taxonomy-pill{background:#f0f7f5;color:#397e68}[data-dimension="T5"] .taxonomy-pill{background:#f6f1fc;color:#7957a8}.taxonomy-pill.inactive,.taxonomy-group.inactive .taxonomy-pill{background:var(--neutral-100);color:var(--neutral-400);text-decoration:line-through}.taxonomy-inline-add{display:flex;align-items:center;gap:7px;margin-top:9px;max-width:260px}.taxonomy-inline-add input,.taxonomy-add-group input,.taxonomy-selected-editor input{box-sizing:border-box;min-width:0;height:30px;padding:0 9px;border:1px solid var(--neutral-200);border-radius:5px;background:var(--surface);font:inherit;font-size:12px;color:var(--neutral-800)}.taxonomy-inline-add input{width:150px}.taxonomy-inline-add button{flex:none;padding:4px 7px;border:0;background:transparent;color:var(--primary-600);font-size:12px}.taxonomy-add-group{display:flex;gap:8px;padding-top:15px;border-top:1px solid var(--neutral-200)}.taxonomy-add-group input{height:32px;width:180px}.taxonomy-add-group .btn{height:32px;font-size:12px}.taxonomy-no-tags{color:var(--neutral-400);font-size:12px}.taxonomy-fixed{display:flex;align-items:center;gap:20px;padding:22px 20px}.taxonomy-fixed-label{color:var(--neutral-500);font-size:13px}.taxonomy-selected-editor{display:flex;align-items:center;gap:12px;margin:0 18px 14px;padding:12px;border:1px solid var(--primary-100);border-radius:7px;background:var(--neutral-50)}.taxonomy-selected-editor>div{display:flex;align-items:center;gap:8px}.taxonomy-selected-editor small{color:var(--neutral-400);font-size:11px}.taxonomy-selected-editor b{font-size:12px;max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.taxonomy-selected-editor input{flex:1;max-width:210px}.taxonomy-selected-editor .text-btn{font-size:12px;white-space:nowrap}.taxonomy-state-action{color:var(--neutral-600)}.taxonomy-state-action.danger{color:var(--danger)}.taxonomy-close{margin-left:auto;border:0;background:transparent;color:var(--neutral-400);font-size:20px}.taxonomy-error{padding:0 18px 12px}@media(max-width:720px){.taxonomy-tabs-row{flex-wrap:wrap;gap:0}.taxonomy-selected-editor{flex-wrap:wrap}.taxonomy-tabs{gap:14px}}
</style>
<style scoped>
.taxonomy-action-popover{position:fixed;z-index:70;box-sizing:border-box;width:164px;max-width:calc(100vw - 16px);padding:5px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface);box-shadow:var(--shadow-3)}
.taxonomy-action-popover.is-form{width:280px;padding:12px}
.taxonomy-action-head{display:flex;align-items:center;gap:8px;min-height:28px;padding:0 7px 4px;border-bottom:1px solid var(--neutral-100);margin-bottom:4px}
.taxonomy-action-head b{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:500;color:var(--neutral-500)}
.taxonomy-action-head .taxonomy-close{flex:none;width:24px;height:24px;padding:0;line-height:24px}
.taxonomy-menu-item{display:flex;align-items:center;width:100%;height:32px;padding:0 9px;border:0;border-radius:5px;background:transparent;color:var(--neutral-600);font:inherit;font-size:12px;text-align:left;cursor:pointer}
.taxonomy-menu-item:hover,.taxonomy-menu-item:focus-visible{background:var(--primary-50);color:var(--primary-600)}
.taxonomy-menu-item.is-danger{color:var(--danger)}
.taxonomy-menu-item.is-danger:hover,.taxonomy-menu-item.is-danger:focus-visible{background:var(--danger-bg);color:var(--danger-hover)}
.taxonomy-action-field{display:flex;flex-direction:column;gap:8px;margin-top:12px;font-size:12px;color:var(--neutral-500)}
.taxonomy-action-field input{box-sizing:border-box;width:100%;min-width:0;height:32px;padding:0 9px;border:1px solid var(--neutral-200);border-radius:6px;color:var(--neutral-900);background:var(--surface);font:inherit;font-size:12px}
.taxonomy-action-footer{display:flex;justify-content:flex-end;gap:8px;margin-top:12px}
.taxonomy-action-footer .btn{min-height:32px;height:32px;padding:0 10px;font-size:12px}
.taxonomy-action-error{margin:8px 4px 3px;font-size:12px;line-height:18px;color:var(--danger)}
</style>
