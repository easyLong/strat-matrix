<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import type { TopicOption } from '../types'
import type { TaxonomyItems } from '../topicTaxonomy'
import TopicLabelDetails from './TopicLabelDetails.vue'
const props = defineProps<{ topic: TopicOption; items: TaxonomyItems }>()
const emit = defineEmits<{ close: [] }>()
const loaded = ref<TopicOption | null>(null)
const loading = ref(false)
const error = ref('')
const panel = ref<HTMLElement | null>(null)
const detail = computed(() => loaded.value ?? props.topic)
const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
let requestId = 0
watch(() => [props.topic.topic_id, props.topic.topic_type], async () => {
  const request = ++requestId
  loaded.value = null; error.value = ''; loading.value = true
  try { const row = await api.topicDetail(props.topic.topic_id, props.topic.topic_type); if (request === requestId) loaded.value = row }
  catch (exc) { if (request === requestId) error.value = exc instanceof Error ? exc.message : '读取选题详情失败' }
  finally { if (request === requestId) loading.value = false }
}, { immediate: true })
function keyboard(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); emit('close'); return }
  if (event.key !== 'Tab') return
  const nodes = panel.value?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), [tabindex="0"]')
  if (!nodes?.length) return
  const first = nodes[0], last = nodes[nodes.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
onMounted(async () => { document.addEventListener('keydown', keyboard, true); await nextTick(); panel.value?.querySelector<HTMLButtonElement>('button')?.focus() })
onBeforeUnmount(() => { requestId++; document.removeEventListener('keydown', keyboard, true); returnFocus?.focus({ preventScroll: true }) })
</script>
<template>
  <Teleport to="body"><div class="drawer-mask topic-detail-mask" @click.self="emit('close')"><aside ref="panel" class="drawer topic-detail-drawer" role="dialog" aria-modal="true" aria-label="选题详情"><div class="drawer-head"><h2>选题详情</h2><button class="icon-btn" type="button" aria-label="关闭选题详情" @click="emit('close')">×</button></div><div class="drawer-body">
    <div class="topic-detail-heading"><span class="topic-detail-id">{{ detail.topic_id }}</span><h3>{{ detail.topic_title }}</h3><div class="topic-detail-meta"><span>{{ detail.content_type || '未设置选题二级分类' }}</span><span>{{ detail.is_marketing ? '营销' : '非营销' }}</span><span v-if="detail.label_status">{{ detail.label_status }}</span></div></div>
    <section class="topic-detail-outline"><h4>选题大纲</h4><p>{{ detail.outline || '暂无选题大纲' }}</p></section>
    <div class="topic-detail-validity"><span>有效期</span><b>{{ detail.valid_from?.slice(0, 10) || '不限' }} 至 {{ detail.valid_to?.slice(0, 10) || '不限' }}</b></div>
    <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div><div v-if="loading" class="topic-detail-loading" role="status">正在读取标签…</div><TopicLabelDetails v-else :topic="detail" :items="items" />
  </div></aside></div></Teleport>
</template>
<style scoped>
.topic-detail-mask{z-index:100}.topic-detail-drawer{width:min(680px,96vw)}.topic-detail-drawer .drawer-body{overflow-y:auto;overscroll-behavior:contain}.topic-detail-heading{padding-bottom:18px}.topic-detail-id{font-size:12px;color:var(--neutral-400)}.topic-detail-heading h3{margin:8px 0 12px;font-size:19px;line-height:1.5}.topic-detail-meta{display:flex;gap:14px;color:var(--neutral-500);font-size:12px}.topic-detail-outline{padding:16px;border:1px solid var(--neutral-200);border-radius:8px;margin-bottom:16px}.topic-detail-outline h4{margin:0 0 9px;font-size:13px}.topic-detail-outline p{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.8;color:var(--neutral-600)}.topic-detail-validity{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 20px;font-size:12px}.topic-detail-validity>span{color:var(--neutral-400)}.topic-detail-validity>b{color:var(--neutral-600);font-weight:400}.topic-detail-loading{padding:24px;color:var(--neutral-400);font-size:13px}
</style>
