const assert = require('node:assert/strict')
const { it: test } = require('mocha')
const fs = require('node:fs')
const path = require('node:path')
const { load, Vue } = require('./helpers/vue2-loader.cjs')
const nextTick = Vue.nextTick
const loadJs = filename => load(path.resolve(__dirname, filename))
const rules = loadJs('../src/ui/lifecycleRules.js')
const calendar = loadJs('../src/ui/planningCalendar.js')
const { configDetailRows, configVersionNumber } = loadJs('../src/ui/configHistory.js')
const { createTopicSelection } = loadJs('../src/models/topicSelection.js')
const { createAccountSelection } = loadJs('../src/models/accountSelection.js')
const { csvCell } = loadJs('../src/ui/csv.js')

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
  const owner = new Vue({ data: () => ({ topics: [
    { topic_id: 'N1', topic_title: 'Alpha', outline: 'Outline A', is_marketing: false, content_type: 'type-a' },
    { topic_id: 'N2', topic_title: 'Beta', is_marketing: false, content_type: 'type-b' },
    { topic_id: 'M1', topic_title: 'Marketing', is_marketing: true, content_type: 'type-a' },
  ], isMarketing: marketing, publishDate: '2026-11-06', today:'2026-11-06', topicReview: false, error: '' }) })
  return { owner, selection: createTopicSelection(owner) }
}

test('topic query is explicit, cumulative selection survives filter changes and return to a saved step', async () => {
  const fixture = selectionFixture()
  try {
    const s = fixture.selection
    s.setTopicSelected('N1', true)
    s.topicQuery = 'Beta'
    assert.equal(s.filteredTopics.length, 2)
    s.applyTopicFilters()
    assert.deepEqual(s.filteredTopics.map(t => t.topic_id), ['N2'])
    s.setTopicSelected('N2', true)
    s.topicQuery = ''
    s.applyTopicFilters()
    await nextTick()
    assert.deepEqual(Array.from(s.selectedTopicIds), ['N1', 'N2'])
    assert.deepEqual(s.selectedTopics.map(t => t.topic_id), ['N1', 'N2'])
  } finally { fixture.selection.$destroy(); fixture.owner.$destroy() }
})

test('saved topic selection freezes both query application and checkbox changes', () => {
  const fixture = selectionFixture()
  try {
    const s = fixture.selection
    s.setTopicSelected('N1', true)
    fixture.owner.topicReview = true
    s.topicQuery = 'Beta'
    s.applyTopicFilters()
    s.setTopicSelected('N2', true)
    s.removeTopic(0)
    assert.equal(s.filteredTopics.length, 2)
    assert.deepEqual(Array.from(s.selectedTopicIds), ['N1'])
  } finally { fixture.selection.$destroy(); fixture.owner.$destroy() }
})

test('marketing type is fixed and rejects nonmarketing topics even if filter state is tampered with', () => {
  const fixture = selectionFixture(true)
  try {
    const s = fixture.selection
    assert.deepEqual(s.filteredTopics.map(t => t.topic_id), ['M1'])
    s.setTopicSelected('M1', true)
    s.topicTypeFilter = 'non_marketing'
    s.applyTopicFilters()
    s.setTopicSelected('N2', true)
    assert.deepEqual(s.filteredTopics.map(t => t.topic_id), ['M1'])
    assert.deepEqual(Array.from(s.selectedTopicIds), ['M1'])
    assert.equal(s.selectedTopics[0].topic_id, 'M1')
    assert.match(fixture.owner.error, /类型或有效期/)
  } finally { fixture.selection.$destroy(); fixture.owner.$destroy() }
})

test('manual topics use publish day for nonmarketing, current Beijing day for marketing, with inclusive boundaries', async () => {
  const { topicValidOn, beijingDate, manualTopicTooltip } = loadJs('../src/ui/manualTopics.js')
  assert.equal(beijingDate(new Date('2026-11-05T16:05:00Z')), '2026-11-06')
  const topic = { topic_id: 'FUTURE', topic_title: 'Future', is_marketing: false, valid_from: '2026-11-05T16:00:00Z', valid_to: '2026-11-07T15:59:59Z' }
  assert.equal(topicValidOn(topic, '2026-11-05'), false)
  assert.equal(topicValidOn(topic, '2026-11-06'), true)
  assert.equal(topicValidOn(topic, '2026-11-07'), true)
  assert.equal(topicValidOn(topic, '2026-11-08'), false)
  assert.equal(topicValidOn({ ...topic, valid_from: 'bad-date' }, '2026-11-06'), false)
  const fixture = selectionFixture()
  try {
    fixture.owner.topics = [topic]
    assert.deepEqual(fixture.selection.filteredTopics.map(t => t.topic_id), ['FUTURE'])
    fixture.selection.setTopicSelected('FUTURE', true)
    fixture.owner.topicReview = true
    fixture.owner.publishDate = '2026-11-08'
    await nextTick()
    assert.equal(fixture.selection.filteredTopics.length, 0)
    assert.equal(fixture.selection.selectedTopicIds.length, 0)
    assert.equal(fixture.owner.topicReview, false)
    assert.match(fixture.owner.error, /已移除/)
  } finally { fixture.selection.$destroy(); fixture.owner.$destroy() }
  let marketingOwner, marketingSelection
  try {
    const marketing = { ...topic, is_marketing: true, topic_title: '', related_activity_id: 'ACT-1', related_activity: '活动名称', activity_organization: '测试分行' }
    const options = marketingOwner = new Vue({ data: () => ({ topics: [marketing], isMarketing: true, publishDate: '2026-11-09', today:'2026-11-06', topicReview:false, error:'' }) })
    const s = marketingSelection = createTopicSelection(options)
    assert.equal(s.filteredTopics.length, 1)
    options.today = '2026-11-08'
    assert.equal(s.filteredTopics.length, 0)
    assert.match(manualTopicTooltip(marketing), /ACT-1/)
    assert.doesNotMatch(manualTopicTooltip(marketing), /选题标题|选题大纲/)
  } finally { marketingSelection?.$destroy(); marketingOwner?.$destroy() }
})

test('nonmarketing selection stays bounded while filters and pagination change', async () => {
  const fixture = selectionFixture()
  try {
    fixture.owner.topics = Array.from({ length: 120 }, (_, index) => ({ topic_id: String(index), topic_title: String(index), is_marketing: false }))
    for (let i = 0; i < 120; i++) fixture.selection.setTopicSelected(String(i), true)
    assert.equal(fixture.selection.selectedTopicIds.length, 100)
    fixture.selection.topicPage = 6
    fixture.selection.topicPageSize = 100
    await nextTick()
    assert.equal(fixture.selection.topicPage, 1)
    assert.equal(fixture.selection.selectedTopicIds.length, 100)
  } finally { fixture.selection.$destroy(); fixture.owner.$destroy() }
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
  const owner = new Vue({ data: () => ({ accounts: [
    { account_id: 'A', account_name: 'Alpha', um_no: 'UM-A', followers: 100 },
    { account_id: 'B', account_name: 'Beta', um_no: 'UM-B', followers: 500 },
    { account_id: 'C', account_name: 'Gamma', um_no: 'UM-C', followers: 300 },
  ], publishDate: '', isMarketing:false, store:{databaseReady:true}, error:'', notice:'', fetchAvailability }) })
  return { owner, selection: createAccountSelection(owner) }
}

test('account quantity only selects after query and excludes accounts planned for the selected date', async () => {
  const fixture = accountFixture(async date => ({ publish_date: date, planned_account_ids: ['B'] }))
  try {
    fixture.owner.publishDate = '2026-11-20'
    await fixture.selection.loadAccountAvailability()
    const s = fixture.selection
    s.targetCount = 2
    assert.deepEqual(Array.from(s.sampledIds), [])
    await s.applyAccountFilters()
    assert.deepEqual(Array.from(s.sampledIds), ['C', 'A'])
    s.accountReview = true
    s.setAccountSelected('A', false)
    assert.deepEqual(Array.from(s.sampledIds), ['C', 'A'])
  } finally { fixture.selection.$destroy(); fixture.owner.$destroy() }
})

test('late account availability responses cannot overwrite a newer publication date', async () => {
  const pending = new Map()
  const fixture = accountFixture(date => new Promise(resolve => pending.set(date, resolve)))
  try {
    fixture.owner.publishDate = '2026-11-20'
    fixture.owner.publishDate = '2026-11-21'
    pending.get('2026-11-21')({ publish_date: '2026-11-21', planned_account_ids: ['C'] })
    await nextTick()
    pending.get('2026-11-20')({ publish_date: '2026-11-20', planned_account_ids: ['A'] })
    await nextTick()
    assert.equal(fixture.selection.availabilityReady, true)
    assert.deepEqual(Array.from(fixture.selection.plannedAccountIds), ['C'])
  } finally { fixture.selection.$destroy(); fixture.owner.$destroy() }
})

test('UM/account-ID import counts data rows and keeps recognized accounts when some rows fail', async () => {
  const fixture = accountFixture(async date => ({ publish_date: date, planned_account_ids: ['B'] }))
  try {
    fixture.owner.publishDate = '2026-11-20'
    await fixture.selection.loadAccountAvailability()
    const csv = 'UM号,账号ID\r\nUM-A,\r\n,C\r\nUM-B,\r\nMISSING,\r\nUM-A,\r\n'
    await fixture.selection.importAccountsByIdentifier(new Blob([csv]))
    const s = fixture.selection
    assert.equal(s.targetCount, 5)
    assert.deepEqual(Array.from(s.sampledIds), ['A', 'C'])
    assert.equal(s.importMatchedCount, 2)
    assert.equal(s.importDuplicateRows.length, 1)
    assert.equal(s.importUnmatchedRows.length, 1)
    assert.equal(s.importPlannedRows.length, 1)
    assert.equal(s.importIssueDialogOpen, true)
  } finally { fixture.selection.$destroy(); fixture.owner.$destroy() }
})
