const assert = require('node:assert/strict')
const { test } = require('node:test')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const { parse, compileScript } = require('@vue/compiler-sfc')
const { createSSRApp, h } = require('vue')
const { renderToString } = require('@vue/server-renderer')

// Render the actual history component, including its table and detail drawer.
function load(file) {
  const source = fs.readFileSync(file, 'utf8')
  const code = file.endsWith('.vue')
    ? compileScript(parse(source, { filename: file }).descriptor, { id: 'history-test', inlineTemplate: true }).content
    : source
  const compiled = ts.transpileModule(code, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
  const module = { exports: {} }
  const localRequire = name => {
    if (name.endsWith('PageBreadcrumbs.vue')) return { default: { render: () => null } }
    if (name.startsWith('.')) return load(path.resolve(path.dirname(file), `${name}.ts`))
    return require(name)
  }
  new Function('require', 'module', 'exports', compiled)(localRequire, module, module.exports)
  return module.exports
}
const History = load(path.resolve(__dirname, '../src/components/config/ConfigHistory.vue')).default
const { canRestoreConfig, configDetailRows } = load(path.resolve(__dirname, '../src/ui/configHistory.ts'))
const latest = {
  version: 19, created_at: '2026-11-03T07:35:01.926Z', created_by: 'tester',
  config: {
    planning_days: [1, 3, 5], schedule_day: 2, schedule_time: '22:00',
    marketing_max: 4, hotspot_ratio: 20, rolling_posts: 10,
    stage_targets: [{ name: '稳定经营期', traffic: 50, conversion: 50 }],
    lifecycle_rules: [{ name: '稳定经营期', catchAll: false, conditions: [{ field: 'followers_count', operator: 'gte', value: 500, join: 'AND' }] }],
  },
}
const oldest = { version: 1, created_at: '2026-09-28 14:31:49', created_by: 'demo-seed', config: { marketing_max: 1, rolling_posts: 10, stage_targets: [] } }
const render = (versions, detail = null) => renderToString(createSSRApp({ render: () => h(History, { versions, detail, disabled: false }) }))

test('incomplete old snapshots cannot break the latest configuration history table', async () => {
  const before = JSON.stringify(oldest)
  const html = await render([latest, oldest])
  assert.match(html, /tester/)
  assert.match(html, /2026-11-03 15:35:01/)
  assert.match(html, /营销上限 4/)
  assert.match(html, /demo-seed/)
  assert.equal(JSON.stringify(oldest), before)
})

test('old snapshot details show unrecorded fields without inventing current defaults', async () => {
  const html = await render([latest, oldest], oldest)
  assert.match(html, /完整配置/)
  assert.match(html, /未记录/)
  assert.ok(!html.includes('每周二 22:00'))
  const rows = configDetailRows(oldest.config)
  assert.equal(rows.find(row => row.key === 'planning_days').value, '未记录')
  assert.equal(rows.find(row => row.key === 'hotspot_ratio').value, '未记录')
  assert.equal(rows.find(row => row.key === 'marketing_max').value, '1 条 / 营销账号 / 周')
})

test('latest history details and changes remain available alongside incomplete snapshots', async () => {
  const html = await render([latest, oldest], latest)
  assert.match(html, /修改摘要/)
  assert.match(html, /完整配置/)
  assert.match(html, /每周二 22:00/)
  assert.match(html, /500/)
})

test('partial snapshots are viewable but cannot be restored as a complete configuration', async () => {
  assert.equal(canRestoreConfig(oldest.config), false)
  const complete = structuredClone(latest.config)
  complete.stage_targets = Array.from({ length: 5 }, () => ({ name: 'stage', traffic: 50, conversion: 50 }))
  complete.lifecycle_rules = Array.from({ length: 5 }, () => ({ name: 'stage', conditions: [], catchAll: true }))
  complete.hotspot_ratio = 0
  complete.marketing_max = 0
  assert.equal(canRestoreConfig(complete), true)
  const html = await render([latest, oldest])
  assert.match(html, /disabled[^>]*title="该版本未记录完整配置，仅支持查看"/)
  assert.equal(configDetailRows(complete).find(row => row.key === 'hotspot_ratio').value, '0%')
})
