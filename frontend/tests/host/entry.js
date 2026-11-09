// Test host only: never imported by the standalone or bank production entry.
import Vue from 'vue';
import Vuex from 'vuex';
import VueRouter from 'vue-router';
import axios from 'axios';
import { createPlanningIntegration, PlanningRequestError } from '../../src/integration';
import '../../src/integration.css';
Vue.use(Vuex);
Vue.use(VueRouter);
const permissions = Vue.observable({ write: true, config: true });
const events = [];
const client = axios.create();
client.interceptors.request.use(config => {
    config.headers.set('X-Test-Host-Session', 'synthetic-session');
    return config;
});
// Simulate an existing host interceptor that already returns response.data.
client.interceptors.response.use(response => response.data);
const store = new Vuex.Store({ state: { hostValue: 'unchanged' } });
const planning = createPlanningIntegration({
    http: client, store, routePrefix: '/operations/planning', apiPrefix: '/fixture-java/api/plan',
    responseMode: 'body',
    unwrapResponse: body => {
        if (body.code !== 'OK')
            throw new PlanningRequestError(body.message, 422);
        return body.payload;
    },
    can: capability => capability === 'config.view' ? permissions.config : capability.endsWith('.view') || permissions.write,
    notify: message => events.push(message),
    onRequestError: error => events.push({ status: error.status, message: error.message }),
});
const router = new VueRouter({ mode: 'history', routes: [
        { path: '/outside', component: Vue.extend({ name: 'HostOutside', render: h => h('div', { attrs: { id: 'outside-page' } }, '宿主其它页面') }) },
        ...planning.routes,
    ] });
window.hostHarness = { router, store, events, permissions };
new Vue({ router, store, render(h) {
        return h('div', [
            h('header', { attrs: { id: 'host-title' } }, '既有数营平台'),
            h('button', { class: ['btn', 'host-sentinel'], attrs: { id: 'host-sentinel' } }, '宿主原有按钮'),
            h('nav', { class: 'host-nav' }, ['/outside', '/operations/planning/config', '/operations/planning/manual', '/operations/planning/results']
                .map(path => h('router-link', { props: { to: path } }, path))),
            h('keep-alive', [h('router-view')]),
        ]);
    } }).$mount('#host');
