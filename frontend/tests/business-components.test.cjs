const assert = require('node:assert/strict')
const { it: test } = require('mocha')
const fs = require('node:fs')
const path = require('node:path')
const { createRequire } = require('node:module')
const requireFrontend = createRequire(path.resolve(__dirname, '../package.json'))
const ts = requireFrontend('typescript')
const Vue = requireFrontend('vue')
const composition = requireFrontend('@vue/composition-api')
Vue.use(composition.default)
const { ref, effectScope, nextTick } = composition

// Exercise the real TypeScript business modules without adding a test framework.
const cache = new Map()
function loadTs(filename) {
  const file = path.resolve(__dirname, filename)
  if (cache.has(file)) return cache.get(file).exports
  const module = { exports: {} }
  cache.set(file, module)
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  }).outputText
  const requireLocal = name => name.startsWith('@/')
    ? loadTs(path.relative(__dirname, path.resolve(__dirname, '../src', `${name.slice(2)}.ts`)))
    : name.startsWith('.')
    ? loadTs(path.relative(__dirname, path.resolve(path.dirname(file), `${name}.ts`)))
    : requireFrontend(name)
  new Function('require', 'module', 'exports', code)(requireLocal, module, module.exports)
  return module.exports
}
const rules = loadTs('../src/ui/lifecycleRules.ts')
const calendar = loadTs('../src/ui/planningCalendar.ts')
const { configDetailRows, configVersionNumber } = loadTs('../src/ui/configHistory.ts')
const { useManualTopicSelection } = loadTs('../src/composables/useManualTopicSelection.ts')
const { useManualAccountSelection } = loadTs('../src/composables/useManualAccountSelection.ts')
const { csvCell } = loadTs('../src/ui/csv.ts')

test('legacy mixed AND/OR conditions preserve every truth-table result after grouping', () => {
  const condition = (field, join) => ({ field, join, operator: 'gte', value: 1 })
  for (const joins of [['AND', 'OR', 'AND'], ['OR', 'AND', 'OR'], ['AND', 'AND', 'OR']]) {
    const original = [condition('a', 'AND'), ...joins.map((join, index) => condition('bcd'[index], join))]
    const rule = { name: 'stage', conditions: structuredClone(original), condition_mode: 'legacy' }
    rules.normalizeLifecycleRule(rule)
    for (let bits = 0; bits < 16; bits++) {
      const values = Object.fromEntries([...'abcd'].map((name, index) => [name, Boolean(bits & 1 << index)]))
      const before = original.slice(1).reduce((value, c) => c.join === 'OR' ? value || values[c.field] : value && values[c.field], values.a)
      const after = rules.lifecycleGroups(rule).some(group => group.every(c => values[c.field]))
      assert.equal(after, before, JSON.stringify({ joins, values }))
    }
    const normalized = JSON.stringify(rule)
    rules.normalizeLifecycleRule(rule)
    assert.equal(JSON.stringify(rule), normalized)
  }
})

test('removing the last condition of a stage keeps a valid nonempty rule', () => {
  const rule = { conditions: [{ field: 'followers_count', join: 'AND', operator: 'gte', value: 50 }], condition_mode: 'grouped' }
  rules.removeLifecycleCondition(rule, 0, 0)
  assert.equal(rule.conditions.length, 1)
})

test('week calendars span year boundaries Monday to Sunday and keep same-day manual and auto plans', () => {
  assert.equal(calendar.weekStart('2027-01-03'), '2026-12-28')
  assert.equal(calendar.weekEnd('2026-12-31'), '2027-01-03')
  const items = [{ id: 1, publish_date: '2026-12-30', plan_type: 'manual' }, { id: 2, publish_date: '2026-12-30', plan_type: 'auto' }]
  const days = calendar.daysFor({ start: '2026-12-28', end: '2027-01-03', items })
  assert.equal(days.length, 7)
  assert.equal(days[0].date, '2026-12-28')
  assert.equal(days[6].date, '2027-01-03')
  assert.deepEqual(days[2].items.map(item => item.id), [1, 2])
})

function selectionFixture(marketing = false) {
  const scope = effectScope()
  const topics = ref([
    { topic_id: 'N1', topic_title: 'Alpha', outline: 'Outline A', is_marketing: false, content_type: 'type-a' },
    { topic_id: 'N2', topic_title: 'Beta', is_marketing: false, content_type: 'type-b' },
    { topic_id: 'M1', topic_title: 'Marketing', is_marketing: true, content_type: 'type-a' },
  ])
  const options = { topics, isMarketing: ref(marketing), publishDate: ref('2026-11-06'), topicReview: ref(false), error: ref('') }
  return { ...options, scope, selection: scope.run(() => useManualTopicSelection(options)) }
}

test('topic query is explicit, cumulative selection survives filter changes and return to a saved step', async () => {
  const fixture = selectionFixture()
  try {
    const s = fixture.selection
    s.setTopicSelected('N1', true)
    s.topicQuery.value = 'Beta'
    assert.equal(s.filteredTopics.value.length, 2)
    s.applyTopicFilters()
    assert.deepEqual(s.filteredTopics.value.map(t => t.topic_id), ['N2'])
    s.setTopicSelected('N2', true)
    s.topicQuery.value = ''
    s.applyTopicFilters()
    await nextTick()
    assert.deepEqual(Array.from(s.selectedTopicIds.value), ['N1', 'N2'])
    assert.deepEqual(s.selectedTopics.value.map(t => t.topic_id), ['N1', 'N2'])
  } finally { fixture.scope.stop() }
})

test('saved topic selection freezes both query application and checkbox changes', () => {
  const fixture = selectionFixture()
  try {
    const s = fixture.selection
    s.setTopicSelected('N1', true)
    fixture.topicReview.value = true
    s.topicQuery.value = 'Beta'
    s.applyTopicFilters()
    s.setTopicSelected('N2', true)
    s.removeTopic(0)
    assert.equal(s.filteredTopics.value.length, 2)
    assert.deepEqual(Array.from(s.selectedTopicIds.value), ['N1'])
  } finally { fixture.scope.stop() }
})

test('marketing type is fixed and rejects nonmarketing topics even if filter state is tampered with', () => {
  const fixture = selectionFixture(true)
  try {
    const s = fixture.selection
    assert.deepEqual(s.filteredTopics.value.map(t => t.topic_id), ['M1'])
    s.setTopicSelected('M1', true)
    s.topicTypeFilter.value = 'non_marketing'
    s.applyTopicFilters()
    s.setTopicSelected('N2', true)
    assert.deepEqual(s.filteredTopics.value.map(t => t.topic_id), ['M1'])
    assert.deepEqual(Array.from(s.selectedTopicIds.value), ['M1'])
    assert.equal(s.selectedTopics.value[0].topic_id, 'M1')
    assert.match(fixture.error.value, /类型或有效期/)
  } finally { fixture.scope.stop() }
})

test('manual topics use publish day for nonmarketing, current Beijing day for marketing, with inclusive boundaries', async () => {
  const { topicValidOn, beijingDate, manualTopicTooltip } = loadTs('../src/ui/manualTopics.ts')
  assert.equal(beijingDate(new Date('2026-11-05T16:05:00Z')), '2026-11-06')
  const topic = { topic_id: 'FUTURE', topic_title: 'Future', is_marketing: false, valid_from: '2026-11-05T16:00:00Z', valid_to: '2026-11-07T15:59:59Z' }
  assert.equal(topicValidOn(topic, '2026-11-05'), false)
  assert.equal(topicValidOn(topic, '2026-11-06'), true)
  assert.equal(topicValidOn(topic, '2026-11-07'), true)
  assert.equal(topicValidOn(topic, '2026-11-08'), false)
  assert.equal(topicValidOn({ ...topic, valid_from: 'bad-date' }, '2026-11-06'), false)
  const fixture = selectionFixture()
  try {
    fixture.topics.value = [topic]
    assert.deepEqual(fixture.selection.filteredTopics.value.map(t => t.topic_id), ['FUTURE'])
    fixture.selection.setTopicSelected('FUTURE', true)
    fixture.topicReview.value = true
    fixture.publishDate.value = '2026-11-08'
    await nextTick()
    assert.equal(fixture.selection.filteredTopics.value.length, 0)
    assert.equal(fixture.selection.selectedTopicIds.value.length, 0)
    assert.equal(fixture.topicReview.value, false)
    assert.match(fixture.error.value, /已移除/)
  } finally { fixture.scope.stop() }
  const scope = effectScope()
  try {
    const marketing = { ...topic, is_marketing: true, topic_title: '', related_activity_id: 'ACT-1', related_activity: '活动名称', activity_organization: '测试分行' }
    const options = { topics: ref([marketing]), isMarketing: ref(true), publishDate: ref('2026-11-09'), today: ref('2026-11-06'), topicReview: ref(false), error: ref('') }
    const s = scope.run(() => useManualTopicSelection(options))
    assert.equal(s.filteredTopics.value.length, 1)
    options.today.value = '2026-11-08'
    assert.equal(s.filteredTopics.value.length, 0)
    assert.match(manualTopicTooltip(marketing), /ACT-1/)
    assert.doesNotMatch(manualTopicTooltip(marketing), /选题标题|选题大纲/)
  } finally { scope.stop() }
})

test('nonmarketing selection stays bounded while filters and pagination change', async () => {
  const fixture = selectionFixture()
  try {
    fixture.topics.value = Array.from({ length: 120 }, (_, index) => ({ topic_id: String(index), topic_title: String(index), is_marketing: false }))
    for (let i = 0; i < 120; i++) fixture.selection.setTopicSelected(String(i), true)
    assert.equal(fixture.selection.selectedTopicIds.value.length, 100)
    fixture.selection.topicPage.value = 6
    fixture.selection.topicPageSize.value = 100
    await nextTick()
    assert.equal(fixture.selection.topicPage.value, 1)
    assert.equal(fixture.selection.selectedTopicIds.value.length, 100)
  } finally { fixture.scope.stop() }
})

test('configuration history compares complete stage targets and lifecycle definitions', () => {
  const config = {
    planning_days: [1, 3, 5], schedule_day: 2, schedule_time: '22:00', marketing_max: 3, hotspot_ratio: 20, rolling_posts: 10,
    stage_targets: [{ name: 'stage', traffic: 80, conversion: 20 }],
    lifecycle_rules: [{ name: 'stage', condition_mode: 'grouped', conditions: [{ field: 'followers_count', operator: 'gte', value: 50, join: 'AND' }] }],
  }
  const rows = configDetailRows(config)
  assert.equal(rows.find(row => row.key === 'stage:stage:traffic').value, '80%')
  assert.match(rows.find(row => row.key === 'lifecycle:stage').value, /50/)
  assert.equal(configVersionNumber({ version: 9 }, [{ version: 9 }, { version: 4 }]), 2)
})

test('failure CSV escapes multiline fields, quotes and spreadsheet formulas', () => {
  assert.equal(csvCell('a,"b"\nc'), '"a,""b""\nc"')
  assert.equal(csvCell('=HYPERLINK("x")'), '"\'=HYPERLINK(""x"")"')
  assert.equal(csvCell('UM123'), '"UM123"')
})

function accountFixture(fetchAvailability) {
  const scope = effectScope()
  const options = {
    accounts: ref([
      { account_id: 'A', account_name: 'Alpha', um_no: 'UM-A', followers: 100 },
      { account_id: 'B', account_name: 'Beta', um_no: 'UM-B', followers: 500 },
      { account_id: 'C', account_name: 'Gamma', um_no: 'UM-C', followers: 300 },
    ]),
    publishDate: ref(''), isMarketing: ref(false), databaseReady: ref(true), error: ref(''), notice: ref(''), fetchAvailability,
  }
  return { ...options, scope, selection: scope.run(() => useManualAccountSelection(options)) }
}

test('account quantity only selects after query and excludes accounts planned for the selected date', async () => {
  const fixture = accountFixture(async date => ({ publish_date: date, planned_account_ids: ['B'] }))
  try {
    fixture.publishDate.value = '2026-11-20'
    await fixture.selection.loadAccountAvailability()
    const s = fixture.selection
    s.targetCount.value = 2
    assert.deepEqual(Array.from(s.sampledIds.value), [])
    await s.applyAccountFilters()
    assert.deepEqual(Array.from(s.sampledIds.value), ['C', 'A'])
    s.accountReview.value = true
    s.setAccountSelected('A', false)
    assert.deepEqual(Array.from(s.sampledIds.value), ['C', 'A'])
  } finally { fixture.scope.stop() }
})

test('late account availability responses cannot overwrite a newer publication date', async () => {
  const pending = new Map()
  const fixture = accountFixture(date => new Promise(resolve => pending.set(date, resolve)))
  try {
    fixture.publishDate.value = '2026-11-20'
    fixture.publishDate.value = '2026-11-21'
    pending.get('2026-11-21')({ publish_date: '2026-11-21', planned_account_ids: ['C'] })
    await nextTick()
    pending.get('2026-11-20')({ publish_date: '2026-11-20', planned_account_ids: ['A'] })
    await nextTick()
    assert.equal(fixture.selection.availabilityReady.value, true)
    assert.deepEqual(Array.from(fixture.selection.plannedAccountIds.value), ['C'])
  } finally { fixture.scope.stop() }
})

test('UM/account-ID import counts data rows and keeps recognized accounts when some rows fail', async () => {
  const fixture = accountFixture(async date => ({ publish_date: date, planned_account_ids: ['B'] }))
  try {
    fixture.publishDate.value = '2026-11-20'
    await fixture.selection.loadAccountAvailability()
    const csv = 'UM号,账号ID\r\nUM-A,\r\n,C\r\nUM-B,\r\nMISSING,\r\nUM-A,\r\n'
    await fixture.selection.importAccountsByIdentifier(new Blob([csv]))
    const s = fixture.selection
    assert.equal(s.targetCount.value, 5)
    assert.deepEqual(Array.from(s.sampledIds.value), ['A', 'C'])
    assert.equal(s.importMatchedCount.value, 2)
    assert.equal(s.importDuplicateRows.value.length, 1)
    assert.equal(s.importUnmatchedRows.value.length, 1)
    assert.equal(s.importPlannedRows.value.length, 1)
    assert.equal(s.importIssueDialogOpen.value, true)
  } finally { fixture.scope.stop() }
})
