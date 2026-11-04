import Vue from 'vue'
import CompositionAPI from '@vue/composition-api'
import ElementUI from 'element-ui'
import BodyPortal from './components/BodyPortal.vue'

/** Shared standalone/host registration; call before mounting these pages. */
export function installPlanningUi(host: typeof Vue = Vue) {
  host.use(CompositionAPI)
  host.use(ElementUI)
  host.component('BodyPortal', BodyPortal)
}
