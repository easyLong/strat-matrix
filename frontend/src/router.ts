import { createRouter, createWebHashHistory, createWebHistory } from 'vue-router'
import ConfigView from './views/ConfigView.vue'
import ManualView from './views/ManualView.vue'
import ResultsHubView from './views/ResultsHubView.vue'

const history = typeof window !== 'undefined' && window.location.protocol === 'file:'
  ? createWebHashHistory()
  : createWebHistory()

export const router = createRouter({
  history,
  routes: [
    { path: '/', redirect: '/config' },
    { path: '/config', component: ConfigView, meta: { title: 'AI策划配置' } },
    { path: '/auto', redirect: '/results' },
    { path: '/manual', component: ManualView, meta: { title: '人工策划' } },
    { path: '/results', component: ResultsHubView, meta: { title: '策划结果' } },
  ],
})

