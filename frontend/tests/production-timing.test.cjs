const assert = require('node:assert/strict')
const { it: test } = require('mocha')
const path = require('node:path')
const { load, Vue } = require('./helpers/vue2-loader.cjs')
const renderer = require('vue-server-renderer').createRenderer()
const Component = load(path.resolve(__dirname, '../src/components/config/ProductionTimingConfig.vue')).default
const { productionTimingValid, productionLeadLabel } = load(path.resolve(__dirname, '../src/ui/productionTiming.ts'))
const { configDetailRows, configValuesEqual } = load(path.resolve(__dirname, '../src/ui/configHistory.ts'))

test('production timing supports same-day, separate types, unset values and strict integer bounds', () => {
  assert.equal(productionLeadLabel(0), 'T−0（投放当天）')
  assert.equal(productionLeadLabel(3), 'T−3（提前 3 天）')
  assert.equal(productionLeadLabel(null), '未配置')
  assert.equal(productionTimingValid({ ordinary: 3, marketing: 0, hotspot: 1 }), true)
  for (const value of [-1, 366, 0.5, NaN, '3']) assert.equal(productionTimingValid({ ordinary: value }), false)
  assert.equal(productionTimingValid({ other: 1 }), false)
  assert.equal(productionTimingValid(undefined), true)
})

test('production timing renders compact readonly values and emits edits without changing saved props', async () => {
  const value = { ordinary: 3, marketing: 0, hotspot: 1 }
  // Portals move DOM nodes in a browser; SSR only needs their slot container.
  const portal = Vue.component('BodyPortal')
  let html
  try {
    Vue.component('BodyPortal', { functional: true, render: (h, context) => h('div', context.children) })
    html = await renderer.renderToString(new Vue({ render: h => h(Component, { props: { value, readonly: true } }) }))
  } finally { Vue.component('BodyPortal', portal) }
  assert.match(html, /普通选题/)
  assert.match(html, /营销选题/)
  assert.match(html, /热点选题/)
  assert.match(html, /T−3/)
  assert.match(html, /T−0/)
  assert.doesNotMatch(html, /<input/)
  const props = Vue.observable({ value, readonly: false })
  const events = []
  const state = Component.setup(props, { emit: (...event) => events.push(event) })
  state.change('ordinary', { target: { value: '5' } })
  assert.deepEqual(events[0], ['input', { ordinary: 5, marketing: 0, hotspot: 1 }])
  assert.equal(value.ordinary, 3)
  props.readonly = true
  state.change('ordinary', { target: { value: '2' } })
  assert.equal(events.length, 1)
})

test('configuration history distinguishes an unrecorded rule from intentionally unset and same-day values', () => {
  assert.equal(configDetailRows({}).find(row => row.key === 'production:ordinary').value, '未记录')
  const rows = configDetailRows({ content_production_lead_days: { ordinary: 3, marketing: 0 } })
  assert.equal(rows.find(row => row.key === 'production:ordinary').value, 'T−3（提前 3 天）')
  assert.equal(rows.find(row => row.key === 'production:marketing').value, 'T−0（投放当天）')
  assert.equal(rows.find(row => row.key === 'production:hotspot').value, '未配置')
})

test('configuration equality ignores API field order without hiding timing or ordered rule changes', () => {
  assert.equal(configValuesEqual({ planning_days: [1, 3], content_production_lead_days: { ordinary: 3, hotspot: 1 } },
    { content_production_lead_days: { hotspot: 1, ordinary: 3 }, planning_days: [1, 3] }), true)
  assert.equal(configValuesEqual({ content_production_lead_days: { ordinary: 0 } },
    { content_production_lead_days: { ordinary: 1 } }), false)
  assert.equal(configValuesEqual({ conditions: [1, 2] }, { conditions: [2, 1] }), false)
})
