<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { usePlanningStore } from './store'

const store = usePlanningStore()
onMounted(() => { void store.initialize() })
const nav = [
  { to: '/config', icon: '▤', label: '策划配置' },
  { to: '/manual', icon: '✎', label: '手动策划' },
  { to: '/results', icon: '▥', label: '策划结果' },
]
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand-mark">✦</div>
      <strong>多账号智能策划</strong>
      <div class="topbar-spacer" />
    </header>
    <div class="workspace">
      <aside class="sidebar">
        <div class="sidebar-title">运营工作台</div>
        <nav aria-label="一级功能导航">
          <RouterLink v-for="item in nav" :key="item.to" :to="item.to" class="nav-item">
            <span class="nav-icon">{{ item.icon }}</span><span>{{ item.label }}</span>
          </RouterLink>
        </nav>
        <div class="sidebar-foot"><span :class="['status-dot', { online: store.databaseReady }]" />{{ store.connectionMessage }}</div>
      </aside>
      <main class="main">
        <div v-if="!store.databaseReady" class="banner warning-banner" role="status">
          {{ store.connectionMessage }}
        </div>
        <RouterView />
      </main>
    </div>
  </div>
</template>

