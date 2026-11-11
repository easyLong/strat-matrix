// Fully synthetic Java HTTP host; no developer database, credentials or model calls.
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const assert = require('node:assert/strict')
require('./helpers/node16.cjs')
const { chromium } = require(process.env.PLANNING_PLAYWRIGHT_MODULE || 'playwright')
const { load } = require('./helpers/vue2-loader.cjs')
const defaults = load(path.resolve(__dirname, '../src/store.js')).defaultConfig
const root = path.resolve(__dirname, '../../run/frontend-host-preview')
const counts = {}
const errors = []
const colorChecks = []
const colorArtifacts = path.resolve(__dirname, '../../run/color-spec-20261111')
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
    else if (api === '/config/query' || api === '/config/save') {
      if (api === '/config/save') { Object.assign(defaults, JSON.parse(body).config); version++ }
      data = config()
    }
    else if (api === '/config/versions/query') data = versions()
    else if (api === '/tag-taxonomy/query') data = { version:1, items:{ T1:[],T2:[],T3:[],T4:[],T5:[] } }
    else if (api === '/accounts/query' || api === '/topics/query') data = []
    else if (api === '/manual-plans/account-availability/query') data = { publish_date:JSON.parse(body).publishDate,planned_account_ids:[] }
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
  page.setDefaultTimeout(10000)
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
    fs.mkdirSync(colorArtifacts, { recursive:true })
    const color = async (selector, property, expected, label=selector, pseudo=null) => {
      const actual = await page.locator(selector).first().evaluate((node, { property, pseudo }) => getComputedStyle(node,pseudo).getPropertyValue(property).trim(), { property, pseudo })
      assert.equal(actual, expected, `${label}: ${property}`)
      colorChecks.push({ label, property, expected, actual })
    }
    await color('.planning-ui', 'background-color', 'rgb(245, 245, 245)', '页面背景 #F5F5F5')
    await color('.config-glance-item', 'background-color', 'rgb(247, 248, 250)', '指标卡 #F7F8FA')
    await color('.config-glance-item>b', 'color', 'rgba(0, 0, 0, 0.9)', '正文 黑色90%')
    await color('.config-glance-item>span', 'color', 'rgba(0, 0, 0, 0.8)', '辅助文字 黑色80%')
    await color('.card-head', 'border-bottom-color', 'rgb(242, 242, 242)', '分割线 #F2F2F2')
    await color('.btn.primary', 'background-color', 'rgb(120, 96, 254)', '品牌色 #7860FE')
    await page.getByRole('button',{name:'编辑配置',exact:true}).hover()
    await page.waitForTimeout(200)
    await color('.btn.primary', 'background-color', 'rgb(78, 26, 165)', '辅助色 #4E1AA5')
    await page.mouse.move(0,0)
    await page.waitForTimeout(200)
    await page.screenshot({ path:path.join(colorArtifacts,'01-config.png'),fullPage:true })
    await page.evaluate(()=>window.hostHarness.mountColorExamples())
    await color('[data-color=primary]', 'background-color', 'rgb(120, 96, 254)')
    await color('[data-color=link]', 'color', 'rgb(120, 96, 254)')
    await color('[data-color=secondary]', 'color', 'rgba(0, 0, 0, 0.6)', '取消/返回 深灰')
    await color('[data-color=disabled]', 'color', 'rgba(0, 0, 0, 0.2)', '不可用 黑色20%')
    await color('[data-color=disabled]', 'opacity', '1', '禁用不重复叠加透明度')
    await color('[data-color=disabled-input]', 'color', 'rgba(0, 0, 0, 0.2)', '禁用输入文字 黑色20%')
    await color('[data-color=disabled-input]', '-webkit-text-fill-color', 'rgba(0, 0, 0, 0.2)', '禁用输入实际填色')
    await color('[data-color=placeholder]', 'color', 'rgba(0, 0, 0, 0.6)', '占位符 黑色60%', '::placeholder')
    for (const [status,value] of [['进行中','rgb(120, 96, 254)'],['已完成','rgb(0, 168, 112)'],['待生产','rgb(255, 178, 13)'],['生产失败','rgb(227, 77, 89)']])
      await color(`[data-status="${status}"]`, 'color', value, status)
    for (const [tone,value] of [['orange','rgb(255, 178, 13)'],['blue','rgb(120, 96, 254)'],['green','rgb(0, 168, 112)'],['red','rgb(227, 77, 89)']])
      await color(`#color-spec-examples .manual-task-table .tag.${tone}`, 'color', value, `人工任务 ${tone}`)
    await color('.status-waiting b', 'color', 'rgb(255, 178, 13)', '内容待生成')
    await color('.status-processing b', 'color', 'rgb(120, 96, 254)', '内容生成中')
    await color('.status-completed b', 'color', 'rgb(0, 168, 112)', '内容已完成')
    await page.locator('#color-spec-examples').screenshot({ path:path.join(colorArtifacts,'02-statuses-and-controls.png') })
    await page.evaluate(()=>window.hostHarness.removeColorExamples())
    assert.equal(await page.locator('.planning-embedded .sidebar').count(),0)
    assert.equal(await page.locator('.planning-embedded .topbar,.planning-embedded .workspace-tabs,.planning-embedded .page-breadcrumb').count(),0,'embedded pages must reuse the host tabs without a second navigation bar')
    assert.equal(await page.locator('#host-sentinel').evaluate(node=>getComputedStyle(node).borderRadius),'1px')
    assert.equal(await page.locator('body').evaluate(node=>getComputedStyle(node).margin),'11px')
    assert.equal(await page.getByRole('button',{name:'编辑配置',exact:true}).evaluate(node=>getComputedStyle(node).borderRadius),'12px')
    await page.getByRole('button',{name:'编辑配置',exact:true}).click()
    await page.getByRole('textbox',{name:'自动策划调度时间',exact:true}).click()
    await page.locator('.planning-picker-popper.el-time-panel:visible').waitFor()
    await color('.planning-picker-popper.el-time-panel .el-time-panel__btn.confirm', 'color', 'rgb(120, 96, 254)', '时间弹层 确认按钮')
    await page.screenshot({ path:path.join(colorArtifacts,'16-config-time-picker.png'),fullPage:true })
    await page.keyboard.press('Escape')
    const scheduleTime = page.getByRole('textbox',{name:'自动策划调度时间',exact:true})
    await scheduleTime.fill('21:35');await scheduleTime.press('Enter')
    assert.equal(await scheduleTime.inputValue(),'21:35')
    assert.equal(await scheduleTime.evaluate(el=>{
      let vm=el.closest('.planning-date-input').__vue__
      while(vm&&vm.$options.name!=='PlanningDateInput')vm=vm.$parent
      return vm.value
    }),'21:35','the business time must stay HH:mm')
    await page.locator('input[type=number]').first().fill('4')
    await page.screenshot({ path:path.join(colorArtifacts,'03-config-edit.png'),fullPage:true })
    await page.evaluate(()=>{void window.hostHarness.router.push('/outside').catch(()=>{})})
    await page.getByRole('alertdialog').waitFor()
    await color('[role=alertdialog] .btn.primary', 'background-color', 'rgb(120, 96, 254)', '继续编辑 使用品牌色')
    await color('[role=alertdialog] .app-confirm-icon', 'color', 'rgb(255, 178, 13)', '确认弹窗 警告色')
    await page.screenshot({ path:path.join(colorArtifacts,'04-leave-confirm.png'),fullPage:true })
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
    await page.screenshot({ path:path.join(colorArtifacts,'05-manual-list.png'),fullPage:true })
    const rangeStart = page.getByLabel('开始时间', { exact:true })
    const rangeEnd = page.getByLabel('截止时间', { exact:true })
    await rangeStart.fill('2026/11/10')
    await rangeStart.press('Enter')
    await rangeEnd.click()
    const rangeCalendar = page.locator('.planning-picker-popper.el-date-picker:visible')
    await rangeCalendar.waitFor()
    assert.ok(await rangeCalendar.locator('td.disabled').count()>0,'the end-date calendar must disable dates before the start date')
    assert.equal(await rangeEnd.getAttribute('type'),'text','date controls must not open a native browser date popup')
    await page.screenshot({ path:path.join(colorArtifacts,'14-date-range.png'),fullPage:true })
    await page.keyboard.press('Escape')
    assert.equal(await page.getByRole('button',{name:'新建人工策划',exact:true}).count(),0)
    await page.evaluate(()=>{window.hostHarness.permissions.write=true})
    await page.getByRole('button',{name:'新建人工策划',exact:true}).click()
    await color('.manual-back', 'color', 'rgba(0, 0, 0, 0.6)', '创建策划 返回按钮')
    await color('.manual-step:disabled', 'color', 'rgba(0, 0, 0, 0.2)', '尚不可进入的步骤')
    await page.screenshot({ path:path.join(colorArtifacts,'06-manual-create.png'),fullPage:true })
    const publishDate = page.getByRole('textbox', { name:/投放日期/ })
    await publishDate.fill('2026/11/27')
    await publishDate.press('Enter')
    await publishDate.click()
    const calendar = page.locator('.planning-picker-popper.el-date-picker:visible')
    await calendar.waitFor()
    await color('.planning-picker-popper.el-date-picker .current:not(.disabled) span', 'background-color', 'rgb(120, 96, 254)', '日期选中态 使用品牌紫')
    await color('.planning-picker-popper.el-date-picker .current:not(.disabled) span', 'color', 'rgb(255, 255, 255)', '日期选中态 白字')
    assert.deepEqual((await calendar.locator('th').allTextContents()).map(t=>t.trim()),['一','二','三','四','五','六','日'])
    await page.screenshot({ path:path.join(colorArtifacts,'15-manual-date-picker.png'),fullPage:true })
    await calendar.locator('td.available:not(.prev-month):not(.next-month)').getByText('28',{ exact:true }).click()
    assert.equal(await publishDate.inputValue(),'2026/11/28')
    assert.equal(await publishDate.evaluate(el=>{
      let vm=el.closest('.planning-date-input').__vue__
      while(vm && vm.$options.name!=='PlanningDateInput')vm=vm.$parent
      return vm.value
    }),'2026-11-28','the business date must stay yyyy-MM-dd')
    const footer = await page.locator('.manual-step-actions').evaluate(el=>({ position:getComputedStyle(el).position,bottom:el.getBoundingClientRect().bottom,height:innerHeight }))
    assert.equal(footer.position,'fixed');assert.ok(Math.abs(footer.bottom-footer.height)<2)
    await publishDate.click()
    await go('/outside')
    await page.locator('.planning-picker-popper:visible').waitFor({ state:'hidden' })
    assert.equal(await page.locator('.planning-picker-popper:visible').count(),0,'cached pages must close their picker popups')
    await go('/operations/planning/manual')
    await page.getByRole('button',{name:'返回',exact:true}).click()
    await go('/outside')
    assert.deepEqual(await page.evaluate(()=>window.testPageListeners.map(item=>item.type)),[])
    assert.equal(await page.evaluate(()=>window.testIntervals.size),0, await page.evaluate(()=>JSON.stringify([...window.testIntervals.values()].map(callback=>callback.toString()))))
    await go('/operations/planning/results')
    await page.getByRole('button',{name:'账号列表',exact:true}).waitFor()
    await color('.result-tabs button.active', 'color', 'rgb(120, 96, 254)', '账号列表 激活态')
    await page.screenshot({ path:path.join(colorArtifacts,'07-results-accounts.png'),fullPage:true })
    await page.getByRole('button',{name:'时间列表',exact:true}).click()
    await page.screenshot({ path:path.join(colorArtifacts,'08-results-periods.png'),fullPage:true })
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
    for (const [width,height] of [[1280,800],[390,844]]) {
      await page.setViewportSize({ width,height })
      await page.screenshot({ path:path.join(colorArtifacts,`09-results-${width}.png`),fullPage:true })
      await color('.planning-ui', 'background-color', 'rgb(245, 245, 245)', `页面背景 ${width}px`)
    }
    fs.writeFileSync(path.join(colorArtifacts,'report.json'),JSON.stringify({ status:'passed', colorChecks, errors },null,2))
    assert.deepEqual(await page.evaluate(()=>window.hostHarness.events),[])
    const artifacts=path.resolve(__dirname,'../../run/frontend-host-acceptance')
    fs.mkdirSync(artifacts,{recursive:true})
    fs.writeFileSync(path.join(artifacts,'report.json'),JSON.stringify({ status:'passed',counts,errors,
      checks:['three-pages','prefixed-navigation','host-axios-wrapper','permissions','css-isolation','cached-portals','cached-timers'] },null,2))
    console.log('Host integration browser acceptance passed')
  } finally { await browser.close(); await new Promise(resolve=>server.close(resolve)) }
})().catch(error=>{console.error(error);server.close();process.exitCode=1})
