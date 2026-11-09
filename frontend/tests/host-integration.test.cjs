const { it: test } = require('mocha')
const assert = require('node:assert/strict')
const path = require('node:path')
const fs = require('node:fs')
const axios = require('axios')
const postcss = require('postcss')
const { load } = require('./helpers/vue2-loader.cjs')
const source = name => load(path.resolve(__dirname, '../src', name))
const runtime = source('host/runtime.ts')

test('explicit POST queries retain view permissions and never grant writes', () => {
  runtime.configurePlanningRuntime({ hosted:true,routePrefix:'/planning',can:permission=>permission==='manual.view' })
  try {
    assert.doesNotThrow(()=>runtime.authorizePlanningRequest('/config/query','POST'))
    assert.doesNotThrow(()=>runtime.authorizePlanningRequest('/manual-plans/tasks/query','POST'))
    assert.throws(()=>runtime.authorizePlanningRequest('/config/save','POST'),/权限/)
    assert.throws(()=>runtime.authorizePlanningRequest('/items/1/replacement-candidates/query','POST'),/权限/)
  } finally { runtime.configurePlanningRuntime({ hosted:false }) }
})

test('host transport is reused without creating a development Axios instance', async () => {
  const original = axios.create
  let created = 0
  axios.create = (...args) => { created++; return original(...args) }
  const requests = source('api/http.ts')
  const calls = []
  try {
    requests.setPlanningHttp({ request: async config => {
      calls.push(config)
      return { data: { code: 'SUCCESS', payload: [1] }, headers: {} }
    } }, { apiPrefix: '/godp/api/plan', unwrapResponse: body => body.payload })
    assert.deepEqual(await requests.request('/query/accounts', { method: 'POST' }), [1])
    assert.equal(calls[0].baseURL, '/godp/api/plan')
    assert.equal(created, 0)
  } finally { axios.create = original; requests.setPlanningHttp() }
})

test('body-mode host clients preserve downloads and expose bounded 429 retry metadata without retrying', async () => {
  const requests = source('api/http.ts')
  let calls = 0
  const blob = new Blob(['xlsx'])
  requests.setPlanningHttp({ request: async () => blob }, { responseMode: 'body' })
  assert.equal(await (await requests.requestBlob('/query/export')).data.text(), 'xlsx')
  requests.setPlanningHttp({ request: async config => {
    calls++
    throw new axios.AxiosError('busy', 'ERR_BAD_REQUEST', config, {},
      { status: 429, data: {}, headers: { 'retry-after': '900' } })
  } })
  try {
    await assert.rejects(requests.request('/health'), error =>
      error.status === 429 && error.retryAfter === 120 && /繁忙/.test(error.message))
    assert.equal(calls, 1)
  } finally { requests.setPlanningHttp() }
})

test('one response keeps its original host binding when another binding is installed', async () => {
  const requests = source('api/http.ts')
  let resolve
  requests.setPlanningHttp({ request: () => new Promise(done => { resolve = done }) },
    { responseMode: 'body', unwrapResponse: body => body.first })
  const first = requests.request('/health')
  requests.setPlanningHttp({ request: async () => ({ second: 2 }) },
    { responseMode: 'body', unwrapResponse: body => body.second })
  try {
    resolve({ first: 1 })
    assert.equal(await first, 1)
    assert.equal(await requests.request('/health'), 2)
  } finally { requests.setPlanningHttp() }
})

test('host capabilities deny writes and exports before making any HTTP request', async () => {
  const requests = source('api/http.ts')
  let calls = 0
  runtime.configurePlanningRuntime({ hosted: true, routePrefix: '/operations/planning', can: p => p.endsWith('.view') })
  requests.setPlanningHttp({ request: async () => { calls++; return { data: {} } } })
  try {
    for (const [url, method] of [['/config/save','POST'], ['/config/versions/1/restore','POST'],
      ['/tag-taxonomy/save','POST'], ['/manual-plans/previews','POST'], ['/query/export','POST'], ['/items/1/replace-topic','POST']]) {
      await assert.rejects(requests.request(url, { method }), error => error.name === 'PlanningPermissionError')
    }
    assert.equal(calls, 0)
    await requests.request('/query/accounts', { method: 'POST' })
    assert.equal(calls, 1)
    runtime.configurePlanningRuntime({ hosted: true, routePrefix: '/operations/planning', can: p => p === 'manual.view' })
    await requests.request('/config/query') // shared bootstrap for manual planning
    await assert.rejects(requests.request('/config/versions/query'), error => error.name === 'PlanningPermissionError')
    assert.equal(calls, 2)
  } finally { runtime.configurePlanningRuntime(); requests.setPlanningHttp() }
})

test('route prefixing preserves task return state, query, hash and existing host paths', () => {
  runtime.configurePlanningRuntime({ routePrefix: '/godp/planning' })
  try {
    const location = { path: '/results', query: { batch: '12', from: 'manual', page: '3' }, hash: '#details' }
    assert.deepEqual(runtime.planningLocation(location), { ...location, path: '/godp/planning/results' })
    assert.equal(runtime.planningLocation('/manual?page=3#list'), '/godp/planning/manual?page=3#list')
    assert.equal(runtime.planningLocation('/godp/planning/manual'), '/godp/planning/manual')
    assert.equal(runtime.planningLocation('/host-other'), '/host-other')
    assert.equal(runtime.localPlanningPath('/godp/planning/results'), '/results')
    assert.equal(runtime.localPlanningPath('/godp/planning-other/results'), '/godp/planning-other/results')
  } finally { runtime.configurePlanningRuntime() }
  assert.throws(() => runtime.configurePlanningRuntime({ hosted: true, routePrefix: '/planning' }))
  assert.throws(() => runtime.configurePlanningRuntime({ routePrefix: '//foreign' }))
})

test('all shared CSS and unscoped App rules are contained by the planning namespace', () => {
  const css = ['style.css','styles/tokens.css','styles/system.css','styles/review.css'].map(name =>
    fs.readFileSync(path.resolve(__dirname, '../src', name), 'utf8'))
  css.push(fs.readFileSync(path.resolve(__dirname, '../src/App.vue'), 'utf8').match(/<style>([\s\S]*?)<\/style>/)[1])
  for (const text of css) postcss.parse(text).walkRules(rule => {
    for (let parent = rule.parent; parent; parent = parent.parent)
      if (parent.type === 'atrule' && /keyframes$/i.test(parent.name)) return
    for (const selector of rule.selectors) assert.ok(selector.includes('.planning-ui') || selector.startsWith('.planning-embedded '), selector)
  })
  assert.equal(fs.readFileSync(path.resolve(__dirname, '../.node-version'), 'utf8').trim(), '16.13.0')
})
