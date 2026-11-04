// Optional browser acceptance driven by the isolated inside Java test host, never the live databases.
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLANNING_PLAYWRIGHT_MODULE || 'playwright')
const root = path.resolve(__dirname, '../dist')
const artifacts = path.resolve(__dirname, '../../run/inside-host-browser')
const backend = new URL(process.argv[2])
const report = { host: 'inside-isolated', pages: [], errors: [], screenshots: [] }

;(async () => {
  fs.mkdirSync(artifacts, { recursive: true })
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost')
    if (url.pathname.startsWith('/api/')) {
      const upstream = http.request(new URL(`/api/plan/${url.pathname.slice(5)}${url.search}`, backend), {
        method: req.method, headers: { ...req.headers, host: backend.host },
      }, response => { res.writeHead(response.statusCode, response.headers); response.pipe(res) })
      upstream.on('error', () => { res.writeHead(502); res.end() })
      req.pipe(upstream)
      return
    }
    const requested = path.resolve(root, `.${decodeURIComponent(url.pathname)}`)
    if (!requested.startsWith(root + path.sep) && requested !== root) { res.writeHead(403); res.end(); return }
    const file = fs.existsSync(requested) && fs.statSync(requested).isFile() ? requested : path.join(root, 'index.html')
    const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2' }
    res.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream')
    fs.createReadStream(file).pipe(res)
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  let browser, page
  try {
    browser = await chromium.launch({ headless: true, executablePath: process.env.PLANNING_CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
    page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    page.setDefaultTimeout(10000)
    page.on('pageerror', error => report.errors.push(error.message))
    const base = `http://127.0.0.1:${server.address().port}`
    const shot = async name => {
      await page.waitForLoadState('networkidle')
      const errors = await page.locator('.error-banner:visible').allTextContents()
      assert.deepEqual(errors, [], `${name}: ${errors.join('; ')}`)
      const file = path.join(artifacts, `${name}.png`)
      await page.screenshot({ path: file, fullPage: true })
      report.screenshots.push(path.basename(file)); report.pages.push(name)
    }
    await page.goto(`${base}/config`)
    await page.getByRole('button', { name: '编辑配置', exact: true }).waitFor()
    assert.ok(await page.getByRole('button', { name: '编辑配置', exact: true }).isEnabled())
    await shot('config-readonly')
    await page.getByRole('button', { name: '历史配置', exact: true }).click()
    await page.getByRole('button', { name: '查看详情', exact: true }).first().click()
    await page.getByRole('dialog').waitFor()
    await shot('config-history')
    await page.locator('.drawer-head button').click()
    await page.getByRole('button', { name: '返回配置', exact: true }).click()
    await page.getByRole('button', { name: '编辑配置', exact: true }).click()
    await shot('config-edit')
    await page.getByRole('button', { name: '取消编辑', exact: true }).click()
    await page.getByRole('button', { name: '确认取消', exact: true }).click()

    await page.goto(`${base}/manual`)
    await page.getByRole('button', { name: '查看策划', exact: true }).first().waitFor()
    await shot('manual-tasks')
    await page.getByRole('button', { name: '新建人工策划', exact: true }).click()
    await page.locator('.manual-create-meta input[type=text]').fill('浏览器隔离验收')
    await page.locator('.manual-create-meta input[type=date]').fill('2026-11-06')
    await page.getByRole('button', { name: '下一步', exact: true }).click()
    await page.getByPlaceholder('请输入计划账号数量').fill('1')
    await page.getByRole('button', { name: '查询', exact: true }).click()
    await page.locator('.manual-account-table tbody input[type=checkbox]:checked').waitFor()
    await shot('manual-accounts')
    await page.getByRole('button', { name: '保存', exact: true }).click()
    await page.getByRole('button', { name: '下一步', exact: true }).click()
    await page.locator('.manual-topic-table tbody input[type=checkbox]').first().check()
    await shot('manual-topics')
    await page.getByRole('button', { name: '保存', exact: true }).click()
    await page.getByRole('button', { name: '下一步', exact: true }).click()
    await page.getByRole('button', { name: '提交人工策划', exact: true }).waitFor()
    await shot('manual-confirm')

    await page.goto(`${base}/results`)
    await page.getByRole('button', { name: '查看策划', exact: true }).first().waitFor()
    await shot('results-accounts')
    await page.getByRole('button', { name: '查看策划', exact: true }).first().click()
    await page.getByText('账号策划详情', { exact: true }).first().waitFor()
    await page.locator('.planning-dashboard').waitFor()
    await page.getByText('选题T2', { exact: true }).first().waitFor()
    await shot('results-account-detail')
    await page.goto(`${base}/results?dimension=period`)
    await page.getByRole('button', { name: '查看策划', exact: true }).first().waitFor()
    await shot('results-periods')
    await page.getByRole('button', { name: '查看策划', exact: true }).first().click()
    await page.getByText('周期策划详情', { exact: true }).first().waitFor()
    await page.locator('.planning-dashboard').waitFor()
    await shot('results-period-detail')
    const tasks = await (await fetch(`${base}/api/query/manual-tasks`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ page: 1, page_size: 10, filters: {} }) })).json()
    const batch = tasks.items.find(task => task.batch_id).batch_id
    await page.goto(`${base}/results?batch=${batch}`)
    await page.locator('.planning-dashboard').waitFor()
    await page.locator('.planning-expand-btn').first().click()
    await page.getByRole('button', { name: '查看计划详情：选题T2', exact: true }).waitFor()
    await shot('results-batch-detail')
    await page.getByRole('button', { name: '查看计划详情：选题T2', exact: true }).click()
    await page.getByRole('dialog').waitFor()
    await shot('results-plan-detail')
    assert.deepEqual(report.errors, [])
    report.status = 'passed'
  } catch (error) {
    report.failure = error.stack
    if (page) {
      report.failedPageText = await page.locator('body').innerText()
      await page.screenshot({ path: path.join(artifacts, 'failed-page.png'), fullPage: true })
    }
    throw error
  } finally {
    fs.writeFileSync(path.join(artifacts, 'report.json'), JSON.stringify(report, null, 2))
    await browser?.close()
    await new Promise(resolve => server.close(resolve))
  }
})().catch(error => { console.error(error); process.exitCode = 1 })
