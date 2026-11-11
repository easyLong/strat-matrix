// Test host only: never imported by the standalone or bank production entry.
import Vue from 'vue';
import Vuex from 'vuex';
import VueRouter from 'vue-router';
import axios from 'axios';
import 'element-ui/lib/theme-chalk/index.css';
import ManualTaskTable from '../../src/components/ManualTaskTable.vue';
import ContentProgress from '../../src/components/ContentProgress.vue';
import { statusTone } from '../../src/ui/status';
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
// Browser-only examples render the production components and shared styles.
// This entry is excluded from the production application and bank delivery.
window.hostHarness.mountColorExamples = () => {
    const node = document.createElement('div');
    document.body.appendChild(node);
    const tasks = ['待生成', '生成中', '已完成', '生成失败'].map((status, index) => ({
        id: index + 1, batch_id: index + 1, task_name: `色系核验 ${status}`,
        batch_code: `COLOR-${index + 1}`, publish_date: '2026-11-11', planned_account_count: 2,
        topic_count: 2, content_status: status, created_by: 'UI-REVIEW',
        created_at: '2026-11-11T10:00:00', updated_at: '2026-11-11T10:00:00',
        content_completed_account_count: status === '已完成' ? 2 : status === '生成中' ? 1 : 0,
        content_failed_count: status === '生成失败' ? 2 : 0,
        failure_count: status === '生成失败' ? 2 : 0,
    }));
    const vm = new Vue({ render(h) {
        return h('section', { class: 'planning-ui', attrs: { id: 'color-spec-examples' } }, [
            h('div', { class: 'main' }, [h('section', { class: 'card' }, [
                h('div', { class: 'card-head' }, [h('h2', '颜色规范核验')]),
                h('div', { class: 'card-body' }, [
                    h('div', { class: 'page-actions' }, [
                        h('button', { class: 'btn primary', attrs: { 'data-color': 'primary' } }, '下一步'),
                        h('button', { class: 'btn', attrs: { 'data-color': 'secondary' } }, '返回'),
                        h('button', { class: 'btn primary', attrs: { disabled: true, 'data-color': 'disabled' } }, '暂不可用'),
                        h('button', { class: 'text-btn', attrs: { 'data-color': 'link' } }, '查看策划'),
                    ]),
                    h('label', { class: 'field' }, [h('span', '查询条件'), h('input', { attrs: { placeholder: '请输入', 'data-color': 'placeholder' } })]),
                    h('label', { class: 'field' }, [h('span', '不可用字段'), h('input', { attrs: { disabled:true, value:'不可用', 'data-color': 'disabled-input' } })]),
                    ...['进行中', '已完成', '待生产', '生产失败'].map(text => h('span', { class: ['tag', statusTone(text)], attrs: { 'data-status': text } }, text)),
                    ...[0, 1, 2].map(completed => h(ContentProgress, { props: { completed, total: 2, display: 'status' } })),
                ]),
                h(ManualTaskTable, { props: { tasks, loading: false, initialized: true, filtered: false } }),
            ])]),
        ]);
    } });
    vm.$mount(node);
    window.hostHarness.removeColorExamples = () => { const el = vm.$el; vm.$destroy(); el.remove(); };
};
new Vue({ router, store, render(h) {
        return h('div', [
            h('header', { attrs: { id: 'host-title' } }, '既有数营平台'),
            h('button', { class: ['btn', 'host-sentinel'], attrs: { id: 'host-sentinel' } }, '宿主原有按钮'),
            h('nav', { class: 'host-nav' }, ['/outside', '/operations/planning/config', '/operations/planning/manual', '/operations/planning/results']
                .map(path => h('router-link', { props: { to: path } }, path))),
            h('keep-alive', [h('router-view')]),
        ]);
    } }).$mount('#host');
