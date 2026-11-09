const { it: test } = require('mocha')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { load, Vue } = require('./helpers/vue2-loader.cjs')
const root = path.resolve(__dirname, '..')
const source = file => load(path.join(root, 'src', file))
const walk = directory => fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry =>
  entry.isDirectory() ? walk(path.join(directory, entry.name)) : [path.join(directory, entry.name)])

test('production source and both build entries use JavaScript and native Vue options only', () => {
  const files = [...walk(path.join(root, 'src')), ...walk(path.join(root, 'tooling')), ...walk(path.join(root, 'tests/host'))]
  assert.deepEqual(files.filter(file => /\.tsx?$/.test(file)), [])
  for (const file of files.filter(file => /\.(js|vue)$/.test(file))) {
    const code = fs.readFileSync(file, 'utf8')
    assert.doesNotMatch(code, /@vue\/composition-api|compat\/composition|lang=["']ts["']|\bsetup\s*\(/, file)
    assert.doesNotMatch(code, /\bdefineComponent\s*\(|\bgetCurrentInstance\s*\(/, file)
  }
  const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'))
  for (const name of ['@vue/composition-api', 'typescript', 'vue-tsc', '@types/node']) {
    assert.equal(pkg.dependencies[name] || pkg.devDependencies[name], undefined, name)
  }
  assert.equal(fs.existsSync(path.join(root, 'tsconfig.json')), false)
  assert.match(fs.readFileSync(path.join(root, 'index.html'), 'utf8'), /src\/main\.js/)
  assert.equal(fs.existsSync(path.join(root, 'vite.config.js')), true)
})

test('native page lifecycle starts once, stops on cache leave, resumes and cleans up on destroy', () => {
  const { bindPageActivity } = source('services/pageActivity.js')
  const page = new Vue()
  let starts = 0, stops = 0
  const activity = bindPageActivity(page, () => starts++, () => stops++)
  page.$emit('hook:mounted')
  page.$emit('hook:activated')
  assert.deepEqual([activity.active, starts, stops], [true, 1, 0])
  page.$emit('hook:deactivated')
  page.$emit('hook:deactivated')
  assert.deepEqual([activity.active, starts, stops], [false, 1, 1])
  page.$emit('hook:activated')
  page.$destroy()
  assert.deepEqual([activity.active, starts, stops], [false, 2, 2])
})

test('a late mounted child cannot restart listeners under a cached inactive ancestor', () => {
  const { bindPageActivity } = source('services/pageActivity.js')
  const parent = new Vue(), child = new Vue({ parent })
  parent._inactive = true
  let starts = 0
  bindPageActivity(child, () => starts++, () => {})
  child.$emit('hook:mounted')
  assert.equal(starts, 0)
  parent._inactive = false
  child.$emit('hook:activated')
  assert.equal(starts, 1)
  child.$destroy(); parent.$destroy()
})

test('list ownership aborts stale requests and prevents late writes after page destruction', async () => {
  const { createAsyncPage } = source('services/asyncPage.js')
  const page = new Vue({ data: () => ({ items: [], total: 0, loading: false }) })
  const pending = [], errors = []
  const query = createAsyncPage(page, signal => new Promise(resolve => pending.push({ signal, resolve })),
    { items: 'items', total: 'total', loading: 'loading' }, message => errors.push(message))
  const first = query.load(), second = query.load()
  assert.equal(pending[0].signal.aborted, true)
  pending[1].resolve({ items: ['new'], total: 1 })
  assert.equal(await second, true)
  pending[0].resolve({ items: ['old'], total: 4 })
  assert.equal(await first, false)
  assert.deepEqual(Array.from(page.items), ['new'])
  assert.equal(page.total, 1)
  const last = query.load()
  page.$destroy()
  pending[2].resolve({ items: ['destroyed'], total: 3 })
  assert.equal(await last, false)
  assert.equal(page.loading, false)
  assert.deepEqual(Array.from(page.items), ['new'])
  assert.deepEqual(errors, [])
})

test('cached lists suspend requests, then resume through native activation events', async () => {
  const { createAsyncPage } = source('services/asyncPage.js')
  const page = new Vue({ data: () => ({ items: [], total: 0, loading: false }) })
  let calls = 0
  const query = createAsyncPage(page, async () => ({ items: [++calls], total: calls }),
    { items: 'items', total: 'total', loading: 'loading' }, assert.fail)
  page.$emit('hook:deactivated')
  assert.equal(await query.load(), false)
  assert.equal(calls, 0)
  page.$emit('hook:activated')
  await Vue.nextTick()
  assert.equal(calls, 1)
  assert.deepEqual(Array.from(page.items), [1])
  page.$destroy()
})
