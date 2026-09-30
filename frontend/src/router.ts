import { createRouter, createWebHistory } from 'vue-router'
import ConfigView from './views/ConfigView.vue'
import AutoView from './views/AutoView.vue'
import ManualView from './views/ManualView.vue'
import ResultsView from './views/ResultsView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/config' },
    { path: '/config', component: ConfigView, meta: { title: '策划配置' } },
    { path: '/auto', component: AutoView, meta: { title: 'AI自动策划' } },
    { path: '/manual', component: ManualView, meta: { title: '手动策划' } },
    { path: '/results', component: ResultsView, meta: { title: '策划结果' } },
  ],
})

