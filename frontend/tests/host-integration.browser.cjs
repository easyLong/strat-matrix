// Fully synthetic Java HTTP host; no developer database, credentials or model calls.
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const assert = require('node:assert/strict')
require('./helpers/node16.cjs')
const { chromium } = require(process.env.PLANNING_PLAYWRIGHT_MODULE || 'playwright')
const { load } = require('./helpers/vue2-loader.cjs')
const defaults = load(path.resolve(__dirname, '../src/store.ts')).defaultConfig
const root = path.resolve(__dirname, '../../run/frontend-host-preview')
const counts = {}
const errors = []
let version = 2
const config = () => ({ config: defaults, version, updated_at: '2026-11-07T09:00:00Z', is_demo: false })
const versions = () => [2,1].map(n => ({ version: n, config: defaults, created_at: '2026-11-07T09:00:00Z', created_by: 'TEST-UM' }))
const server = http.createServer(async (req,res) => {
  const url = new URL(req.url, 'http://localhost')
  if (url.pathname.startsWith('/fixture-java/api/plan/')) {
    const api = url.pathname.slice('/fixture-java/api/plan'.length)
    counts[api] = (counts[api] || 0) + 1
    if (req.headers['x-test-host-session'] !== 'synthetic-session') { res.writeHead(401);res.end();return }
    let body = ''; for await (const part of req) body += part
    let data
    if (api === '/health') data = { service:'java-test', database:'ok' }
    else if (api === '/config') {
      if (req.method === 'PUT') { Object.assign(defaults, JSON.parse(body)); version++ }
      data = config()
    }
    else if (api === '/config/versions') data = versions()
    else if (api === '/tag-taxonomy') data = { version:1, items:{ T1:[],T2:[],T3:[],T4:[],T5:[] } }
    else if (api === '/accounts' || api === '/topics') data = []
    else if (api === '/query/period-context') data = []
    else if (api.startsWith('/query/')) data = { items:[],total:0,page:1,page_size:10,
      summary:{ accounts:0,batches:0,topics:0 }, distribution:[], accounts:[], content_types:[], facets:{ organizations:[],platforms:[],lifecycles:[] } }
    else { res.writeHead(404); res.end(JSON.stringify({ detail:'unhandled test path' }));return }
    res.setHeader('Content-Type','application/json')
    res.end(JSON.stringify({ code:'OK',payload:data }))
    return
  }
  const target = path.resolve(root, '.' + url.pathname)
  const file = target.startsWith(root+path.sep) && fs.existsSync(target) && fs.statSync(target).isFile()
    ? target : path.join(root,'index.html')
  res.setHeader('Content-Type', ({ '.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css' })[path.extname(file)] || 'application/octet-stream')
  fs.createReadStream(file).pipe(res)
})
;(async () => {
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve))
  const browser = await chromium.launch({ headless:true,
    executablePath:process.env.PLANNING_CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
  const page = await browser.newPage({ viewport:{ width:1440,height:1000 } })
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.text().includes('[Vue warn]')) errors.push(message.text()) })
  await page.addInitScript(() => {
    const callbacks = new Map()
    const start = window.setInterval.bind(window), stop = window.clearInterval.bind(window)
    window.setInterval = ((callback, ms, ...args) => {
      const id = start(callback,ms,...args); callbacks.set(id,callback); return id
    })
    window.clearInterval = id => { callbacks.delete(id);stop(id) }
    window.testIntervals = callbacks
    const listeners = []
    for (const [target, names] of [[window,['resize','scroll','focus','beforeunload']],
      [document,['pointerdown','keydown','visibilitychange']]]) {
      const add = target.addEventListener.bind(target), remove = target.removeEventListener.bind(target)
      const capture = options => typeof options === 'boolean' ? options : Boolean(options && options.capture)
      target.addEventListener = (type, listener, options) => {
        if (names.includes(type) && !listeners.some(item => item.target===target && item.type===type && item.listener===listener && item.capture===capture(options)))
          listeners.push({ target,type,listener,capture:capture(options) })
        add(type,listener,options)
      }
      target.removeEventListener = (type, listener, options) => {
        const index = listeners.findIndex(item => item.target===target && item.type===type && item.listener===listener && item.capture===capture(options))
        if (index>=0) listeners.splice(index,1)
        remove(type,listener,options)
      }
    }
    window.testPageListeners = listeners
  })
  const base = 'http://127.0.0.1:' + server.address().port
  const go = async suffix => {
    await page.evaluate(path => window.hostHarness.router.push(path).catch(()=>{}), suffix)
    await page.waitForLoadState('networkidle')
  }
  try {
    await page.goto(base+'/operations/planning/config')
    await page.getByRole('button',{name:'编辑配置',exact:true}).waitFor()
    assert.equal(await page.locator('.planning-embedded .sidebar').count(),0)
    assert.equal(await page.locator('.planning-embedded .topbar,.planning-embedded .workspace-tabs,.planning-embedded .page-breadcrumb').count(),0,'embedded pages must reuse the host tabs without a second navigation bar')
    assert.equal(await page.locator('#host-sentinel').evaluate(node=>getComputedStyle(node).borderRadius),'1px')
    assert.equal(await page.locator('body').evaluate(node=>getComputedStyle(node).margin),'11px')
    assert.equal(await page.getByRole('button',{name:'编辑配置',exact:true}).evaluate(node=>getComputedStyle(node).borderRadius),'12px')
    await page.getByRole('button',{name:'编辑配置',exact:true}).click()
    await page.locator('input[type=number]').first().fill('4')
    await page.evaluate(()=>{void window.hostHarness.router.push('/outside').catch(()=>{})})
    await page.getByRole('button',{name:'放弃修改并离开',exact:true}).click()
    await page.locator('#outside-page').waitFor()
    await go('/operations/planning/config')
    await page.getByRole('button',{name:'编辑配置',exact:true}).waitFor()
    await page.getByRole('button',{name:'历史配置',exact:true}).click()
    await page.getByRole('button',{name:'查看详情',exact:true}).first().click()
    await page.getByRole('dialog').waitFor()
    await go('/outside')
    assert.equal(await page.getByRole('dialog').count(),0)
    assert.deepEqual(await page.evaluate(()=>window.testPageListeners.map(item=>item.type)),[])
    assert.equal(await page.evaluate(()=>window.testIntervals.size),0, await page.evaluate(()=>JSON.stringify([...window.testIntervals.values()].map(callback=>callback.toString()))))
    await go('/operations/planning/config')
    await page.getByRole('dialog').waitFor()
    await page.locator('.drawer-head button').click()
    await page.getByRole('button',{name:'返回配置',exact:true}).click()
    await page.evaluate(()=>{window.hostHarness.permissions.write=false})
    assert.equal(await page.getByRole('button',{name:'编辑配置',exact:true}).count(),0)
    await go('/operations/planning/manual')
    await page.getByText('策划任务列表',{exact:true}).first().waitFor()
    assert.equal(await page.getByRole('button',{name:'新建人工策划',exact:true}).count(),0)
    await page.evaluate(()=>{window.hostHarness.permissions.write=true})
    await page.getByRole('button',{name:'新建人工策划',exact:true}).click()
    await page.getByRole('button',{name:'返回',exact:true}).click()
    await go('/outside')
    assert.deepEqual(await page.evaluate(()=>window.testPageListeners.map(item=>item.type)),[])
    assert.equal(await page.evaluate(()=>window.testIntervals.size),0, await page.evaluate(()=>JSON.stringify([...window.testIntervals.values()].map(callback=>callback.toString()))))
    await go('/operations/planning/results')
    await page.getByRole('button',{name:'账号列表',exact:true}).waitFor()
    await page.getByRole('button',{name:'时间列表',exact:true}).click()
    assert.ok(page.url().includes('/operations/planning/results'))
    await go('/operations/planning/results?account=TEST-ACCOUNT')
    await page.getByText('账号策划详情',{exact:true}).first().waitFor()
    await page.getByRole('button',{name:'返回账号列表',exact:true}).click()
    assert.ok(page.url().includes('/operations/planning/results'))
    await page.evaluate(()=>{window.hostHarness.permissions.config=false})
    const beforeDenied = page.url()
    await go('/operations/planning/config')
    assert.equal(page.url(),beforeDenied)
    assert.deepEqual(await page.evaluate(()=>window.hostHarness.events),['没有访问该页面的权限'])
    await page.evaluate(()=>{window.hostHarness.events.length=0})
    await go('/outside')
    assert.deepEqual(await page.evaluate(()=>window.testPageListeners.map(item=>item.type)),[])
    assert.equal(await page.evaluate(()=>window.testIntervals.size),0)
    assert.deepEqual(errors,[])
    assert.deepEqual(await page.evaluate(()=>window.hostHarness.events),[])
    const artifacts=path.resolve(__dirname,'../../run/frontend-host-acceptance')
    fs.mkdirSync(artifacts,{recursive:true})
    fs.writeFileSync(path.join(artifacts,'report.json'),JSON.stringify({ status:'passed',counts,errors,
      checks:['three-pages','prefixed-navigation','host-axios-wrapper','permissions','css-isolation','cached-portals','cached-timers'] },null,2))
    console.log('Host integration browser acceptance passed')
  } finally { await browser.close(); await new Promise(resolve=>server.close(resolve)) }
})().catch(error=>{console.error(error);server.close();process.exitCode=1})
