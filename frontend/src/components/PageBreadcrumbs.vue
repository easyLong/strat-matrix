<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { pageBreadcrumbsKey, type PageBreadcrumb } from '../composables/usePageBreadcrumbs'

const props = defineProps<{ items?: PageBreadcrumb[]; compact?: boolean }>()
const inherited = inject(pageBreadcrumbsKey, computed(() => []))
const entries = computed(() => props.items ?? inherited.value)
const navigation = ref<HTMLElement | null>(null)
let resizeObserver: ResizeObserver | undefined
function showCurrentLocation() {
  if (navigation.value) navigation.value.scrollLeft = navigation.value.scrollWidth
}
watch(() => entries.value.map(item => item.label).join('>'), async () => {
  await nextTick()
  showCurrentLocation()
}, { immediate: true, flush: 'post' })
onMounted(() => {
  resizeObserver = new ResizeObserver(showCurrentLocation)
  if (navigation.value) resizeObserver.observe(navigation.value)
})
onBeforeUnmount(() => resizeObserver?.disconnect())
function activate(item: PageBreadcrumb) {
  item.beforeNavigate?.()
  void item.action?.()
}
</script>

<template>
  <nav ref="navigation" class="breadcrumb page-breadcrumb" :class="{ compact }" :aria-label="compact ? '详情位置' : '当前位置'">
    <template v-for="(item, index) in entries" :key="`${index}-${item.label}`">
      <svg v-if="index" width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m6 4 4 4-4 4" /></svg>
      <span v-if="index === entries.length - 1" aria-current="page">{{ item.label }}</span>
      <button v-else-if="item.action" type="button" @click="activate(item)">{{ item.label }}</button>
      <RouterLink v-else-if="item.to" :to="item.to" aria-current-value="false" @click="activate(item)">{{ item.label }}</RouterLink>
      <span v-else>{{ item.label }}</span>
    </template>
  </nav>
</template>

<style scoped>
.page-breadcrumb{min-width:0;max-width:100%;overflow-x:auto;white-space:nowrap;scrollbar-width:thin}
.page-breadcrumb>*{flex-shrink:0}
.page-breadcrumb a,.page-breadcrumb button{padding:0;border:0;background:transparent;color:inherit;font:inherit;text-decoration:none;cursor:pointer}
.page-breadcrumb a:hover,.page-breadcrumb button:hover{color:var(--primary-600)}
.page-breadcrumb a:focus-visible,.page-breadcrumb button:focus-visible{outline:2px solid var(--primary-600);outline-offset:2px;border-radius:2px}
.page-breadcrumb [aria-current=page]{color:var(--neutral-600);font-weight:500}
.page-breadcrumb.compact{margin-bottom:16px;font-size:12px}
</style>
