<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { usePlanningStore } from './store'

const store = usePlanningStore()
const route = useRoute()
onMounted(() => { void store.initialize() })
const nav = [
  { to: '/config', icon: 'M4 6h16M4 12h16M4 18h16M9 3v6m6 0v6m-7 0v6', label: 'AI策划配置' },
  { to: '/manual', icon: 'm15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15z', label: '人工策划' },
  { to: '/results', icon: 'M4 4h16v16H4zM9 4v16M4 10h16M13 14h3m-3 3h3', label: '策划结果' },
]
</script>

<template>
  <div class="app-shell">
      <aside class="sidebar">
        <div class="sidebar-brand"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="m6 18 9-9m-5-4 1-3 1 3 3 1-3 1-1 3-1-3-3-1zM17 14l1-2 1 2 2 1-2 1-1 2-1-2-2-1z" /></svg></span><strong>多账号智能策划</strong></div>
        <div class="sidebar-title">运营工作台</div>
        <nav aria-label="一级功能导航">
          <RouterLink v-for="item in nav" :key="item.to" :to="item.to" class="nav-item">
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="item.icon" /></svg><span>{{ item.label }}</span>
          </RouterLink>
        </nav>
        <div class="sidebar-foot"><span :class="['status-dot', { online: store.databaseReady }]" />{{ store.connectionMessage }}</div>
      </aside>
    <div class="app-main-shell">
      <header class="topbar"><nav class="breadcrumb" aria-label="当前位置"><span>运营工作台</span><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m6 4 4 4-4 4" /></svg><span aria-current="page">{{ route.meta.title }}</span></nav></header>
      <main class="main">
        <div v-if="store.initialized && !store.databaseReady" class="banner warning-banner" role="status">
          {{ store.connectionMessage }}
        </div>
        <RouterView />
      </main>
    </div>
  </div>
</template>

