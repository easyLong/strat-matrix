import { createRouter, createWebHistory } from 'vue-router'
import ConfigView from './views/ConfigView.vue'
import ManualView from './views/ManualView.vue'
import ResultsView from './views/ResultsView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/config' },
    { path: '/config', component: ConfigView, meta: { title: 'AI策划配置' } },
    { path: '/auto', redirect: '/results' },
    { path: '/manual', component: ManualView, meta: { title: '人工策划' } },
    { path: '/results', component: ResultsView, meta: { title: '策划结果' } },
  ],
})

