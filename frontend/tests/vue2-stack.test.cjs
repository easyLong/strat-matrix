const { it: test } = require('mocha')
const assert = require('node:assert/strict')
const path = require('node:path')
const { load, Vue, composition } = require('./helpers/vue2-loader.cjs')
const axios = require('axios')
const Vuex = require('vuex')
const source = name => load(path.resolve(__dirname, '../src', name))
const requests = source('api/http.ts')

test('the runtime and matching compiler use the required Vue 2.6 dependency versions', () => {
  assert.equal(process.versions.node, '16.13.0')
  assert.equal(Vue.version, '2.6.14')
  assert.equal(require('vue-template-compiler/package.json').version, Vue.version)
  assert.equal(Vuex.version, '3.6.0')
  assert.equal(axios.VERSION, '1.8.2')
  assert.equal(require('element-ui/package.json').version, '2.15.13')
})

test('Axios keeps the Java API prefix and returns the server payload', async () => {
  let captured
  const create = axios.create
  axios.create = options => create({ ...options, adapter: async config => {
    captured = config
    return { data: { items: [1] }, status: 200, statusText: 'OK', headers: {}, config }
  } })
  try {
    assert.deepEqual(await requests.request('/query/accounts', { method: 'POST', body: JSON.stringify({ page: 2 }) }), { items: [1] })
    assert.equal(captured.baseURL, '/api')
    assert.equal(captured.url, '/query/accounts')
    assert.equal(captured.data, '{"page":2}')
  } finally { axios.create = create }
})

test('Axios preserves Chinese validation failures and represents cancellation as AbortError', async () => {
  requests.setPlanningHttp(axios.create({ adapter: async config => {
    throw new axios.AxiosError('status failure', 'ERR_BAD_REQUEST', config, {}, { status: 422, data: { detail: '账号不可参与策划' }, headers: {}, config })
  } }))
  try {
    await assert.rejects(requests.request('/query/accounts'), /账号不可参与策划/)
    const controller = new AbortController(); controller.abort()
    await assert.rejects(requests.request('/query/accounts', { signal: controller.signal }), error => error.name === 'AbortError')
  } finally { requests.setPlanningHttp() }
})

test('the host Axios client can be injected without editing business calls', async () => {
  const client = axios.create({ baseURL: '/bank/planning', adapter: async config => ({ data: { ok: true }, status: 200, statusText: 'OK', headers: {}, config }) })
  requests.setPlanningHttp(client)
  try { assert.deepEqual(await requests.request('/health'), { ok: true }) }
  finally { requests.setPlanningHttp() }
})

test('report downloads reuse the host prefix and authentication interceptor and preserve file bytes', async () => {
  let captured
  const data = new Blob(['spreadsheet-bytes'], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  const client = axios.create({ baseURL: '/bank/planning', adapter: async config => {
    captured = config
    return { data, status: 200, statusText: 'OK', headers: { 'content-type': data.type }, config }
  } })
  client.interceptors.request.use(config => { config.headers.set('X-Host-Session', 'test-session'); return config })
  requests.setPlanningHttp(client)
  try {
    const response = await requests.requestBlob('/query/export', { method: 'POST', body: JSON.stringify({ format: 'xlsx' }) })
    assert.equal(captured.baseURL, '/bank/planning')
    assert.equal(captured.url, '/query/export')
    assert.equal(captured.headers.get('X-Host-Session'), 'test-session')
    assert.equal(captured.responseType, 'blob')
    assert.equal(await response.data.text(), 'spreadsheet-bytes')
    assert.equal(response.headers['content-type'], data.type)
  } finally { requests.setPlanningHttp() }
})

test('download errors decode JSON blobs and handle non-JSON gateway failures', async () => {
  let body = new Blob([JSON.stringify({ detail: '所选范围无可导出数据' })], { type: 'application/json' })
  const client = axios.create({ adapter: async config => {
    throw new axios.AxiosError('export failed', 'ERR_BAD_RESPONSE', config, {}, { status: 502, data: body, headers: {}, config })
  } })
  requests.setPlanningHttp(client)
  try {
    await assert.rejects(requests.requestBlob('/query/export'), /所选范围无可导出数据/)
    body = new Blob(['<html>Bad Gateway</html>'], { type: 'text/html' })
    await assert.rejects(requests.requestBlob('/query/export'), /请求失败（502）/)
  } finally { requests.setPlanningHttp() }
})

test('Vuex owns page state and can attach the same module to a host store', async () => {
  const { usePlanningStore, attachPlanningStore, planningStore } = source('store.ts')
  const facade = usePlanningStore()
  facade.manualCreating = true
  assert.equal(planningStore.state.stratMatrix.manualCreating, true)
  const host = new Vuex.Store({ state: { unrelated: 'kept' } })
  attachPlanningStore(host)
  try {
    facade.manualCreating = true
    facade.manualTaskListState = { page: 3, pageSize: 10, filters: {} }
    await Vue.nextTick()
    assert.equal(host.state.stratMatrix.manualCreating, true)
    assert.equal(facade.manualTaskListState.page, 3)
    assert.equal(host.state.unrelated, 'kept')
  } finally { attachPlanningStore(planningStore) }
})

test('marketing quantity and review emit updates rather than mutating Vue 2 props', () => {
  const TopicStep = source('components/manual/ManualTopicStep.vue').default
  const events = []
  const props = Vue.observable({ marketing: true, allocationCount: '', review: false, selection: {} })
  const scope = composition.effectScope()
  try {
    const setup = scope.run(() => TopicStep.setup(props, { emit: (...args) => events.push(args) }))
    setup.allocationCountModel.value = 12
    setup.topicReview.value = true
    assert.equal(props.allocationCount, '')
    assert.deepEqual(events, [['update:allocationCount', 12], ['update:review', true]])
  } finally { scope.stop() }
})
