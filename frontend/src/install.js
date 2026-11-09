import Vue from 'vue';
import ElementUI from 'element-ui';
import BodyPortal from './components/BodyPortal.vue';
/** Shared standalone/host registration; call before mounting these pages. */
export function installPlanningUi(host = Vue, options = {}) {
    if (options.elementUI !== false)
        host.use(ElementUI);
    host.component('BodyPortal', BodyPortal);
}
