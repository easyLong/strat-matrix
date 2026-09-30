<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { usePlanningStore } from './store'

const store = usePlanningStore()
onMounted(() => { void store.initialize() })
const currentPeriod = computed(() => {
  const today = new Date()
  const monday = new Date(today)
  monday.setDate(today.getDate() - (today.getDay() + 6) % 7)
  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  const format = (value: Date) => `${value.getMonth() + 1}.${String(value.getDate()).padStart(2, '0')}`
  return `当前周期 · ${format(monday)}–${format(sunday)}`
})

const nav = [
  { to: '/config', icon: '▤', label: '策划配置' },
  { to: '/auto', icon: '✧', label: 'AI自动策划' },
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
      <div class="topbar-meta"><span class="period-chip">{{ currentPeriod }}</span><span class="operator-avatar">运</span><span class="operator-name">运营人员</span><span class="version-chip">开发版 · V0.4</span></div>
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
          {{ store.connectionMessage }}。配置和批次操作将在数据库可用后启用。
        </div>
        <RouterView />
      </main>
    </div>
  </div>
</template>

