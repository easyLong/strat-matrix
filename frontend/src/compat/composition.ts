/** Vue 2.6 reactivity boundary. Register once before evaluating business composables. */
import Vue from 'vue'
import CompositionAPI from '@vue/composition-api'
Vue.use(CompositionAPI)
export * from '@vue/composition-api'

let sequence = 0
export function useId(): string { return `planning-${++sequence}` }
