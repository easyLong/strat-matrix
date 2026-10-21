<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api, type ContentProductionTask } from '../api'
import { formatDateTime } from '../planningTime'
const props = defineProps<{ batchId: number }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const tasks = ref<ContentProductionTask[]>([])
const error = ref('')
const loading = ref(true)
const panel = ref<HTMLElement | null>(null)
const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
let timer: number | undefined
let disposed = false
let fingerprint = ''
const labels: Record<string, string> = { accepted: '生产中', processing: '生产中', completed: '已完成', failed: '生产失败' }
async function load() {
  try {
    const result = await api.contentProductionFlow(props.batchId)
    if (disposed) return
    const next = result.tasks.map(task => `${task.production_task_id}:${task.status}`).join('|')
    if (fingerprint && next !== fingerprint) emit('changed')
    fingerprint = next
    tasks.value = result.tasks
    error.value = ''
  } catch (exc) { if (!disposed) error.value = exc instanceof Error ? exc.message : '读取内容流水失败' }
  finally { if (!disposed) loading.value = false }
}
function keyboard(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); emit('close'); return }
  if (event.key !== 'Tab') return
  const nodes = panel.value?.querySelectorAll<HTMLElement>('button:not(:disabled), [tabindex="0"]')
  if (!nodes?.length) return
  if (event.shiftKey && document.activeElement === nodes[0]) { event.preventDefault(); nodes[nodes.length - 1]?.focus() }
  else if (!event.shiftKey && document.activeElement === nodes[nodes.length - 1]) { event.preventDefault(); nodes[0]?.focus() }
}
onMounted(() => {
  void load(); panel.value?.querySelector('button')?.focus()
  timer = window.setInterval(() => { if (tasks.value.some(task => ['accepted', 'processing'].includes(task.status))) void load() }, 3000)
  document.addEventListener('keydown', keyboard, true)
})
onBeforeUnmount(() => { disposed = true; window.clearInterval(timer); document.removeEventListener('keydown', keyboard, true); previousFocus?.focus({ preventScroll: true }) })
</script>
<template>
  <Teleport to="body"><div class="drawer-mask content-flow-mask" @click.self="emit('close')"><aside ref="panel" class="drawer content-flow-drawer" role="dialog" aria-modal="true" aria-label="内容流水">
    <div class="drawer-head"><h2>内容流水</h2><button class="icon-btn" aria-label="关闭内容流水" @click="emit('close')">×</button></div>
    <div class="drawer-body">
      <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
      <div v-if="loading" role="status">加载中…</div>
      <div v-else-if="!tasks.length" class="empty-state">暂无内容流水</div>
      <article v-for="task in tasks" :key="task.production_task_id" class="content-flow-item">
        <div class="content-flow-heading"><b>{{ task.request.topic.title }}</b><span :class="['tag', task.status === 'completed' ? 'green' : task.status === 'failed' ? 'red' : 'blue']">{{ labels[task.status] || task.status }}</span></div>
        <p>{{ task.request.account.account_name }} · {{ task.request.planning.publish_date }}</p>
        <div class="content-flow-meta"><span v-if="task.provider === 'local_mock'" class="tag gray">本地模拟</span><small>{{ task.production_task_id }}</small></div>
        <div class="content-flow-time"><span>受理 {{ formatDateTime(task.accepted_at) }}</span><span v-if="task.completed_at">完成 {{ formatDateTime(task.completed_at) }}</span></div>
        <p v-if="task.last_error" class="content-flow-error">{{ task.last_error }}</p>
        <details v-if="task.response.body"><summary>查看内容</summary><p class="content-flow-body">{{ task.response.body }}</p></details>
      </article>
    </div>
  </aside></div></Teleport>
</template>
<style scoped>
.content-flow-mask{z-index:110}.content-flow-drawer{width:min(720px,96vw)}.content-flow-drawer .drawer-body{overflow-y:auto}.content-flow-item{padding:16px;border:1px solid var(--neutral-200);border-radius:8px;margin-bottom:14px}.content-flow-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.content-flow-heading b{font-size:14px;line-height:22px}.content-flow-heading .tag{flex:none}.content-flow-item p{font-size:13px;color:var(--neutral-500);line-height:22px}.content-flow-meta{display:flex;align-items:center;gap:8px;overflow-wrap:anywhere}.content-flow-meta small,.content-flow-time{font-size:12px;color:var(--neutral-400)}.content-flow-time{display:flex;flex-wrap:wrap;gap:12px;margin-top:12px}.content-flow-item details{margin-top:12px;font-size:13px}.content-flow-item summary{cursor:pointer;color:var(--primary-600)}.content-flow-body{white-space:pre-wrap}.content-flow-error{color:var(--danger)!important}
</style>
