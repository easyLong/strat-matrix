// Optional browser acceptance driven by the isolated inside Java test host, never the live databases.
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLANNING_PLAYWRIGHT_MODULE || 'playwright')
const root = path.resolve(__dirname, '../dist')
const artifacts = path.resolve(__dirname, '../../run/inside-host-browser')
const backend = new URL(process.argv[2])
const report = { host: 'inside-isolated', node: process.version, pages: [], errors: [], screenshots: [] }

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
    page.on('console', message => {
      if (message.text().includes('[Vue warn]')) report.errors.push(message.text())
    })
    const base = `http://127.0.0.1:${server.address().port}`
    const shot = async name => {
      await page.waitForLoadState('networkidle')
      const visibleText = await page.locator('body').innerText()
      assert.doesNotMatch(visibleText, /&#(?:x[0-9a-f]+|\d+);/i, `${name}: encoded text leaked into the page`)
      const encodedAttributes = await page.locator('[placeholder], [title], [aria-label]').evaluateAll(nodes =>
        nodes.flatMap(node => ['placeholder', 'title', 'aria-label'].map(key => node.getAttribute(key) || ''))
          .filter(value => /&#(?:x[0-9a-f]+|\d+);/i.test(value)))
      assert.deepEqual(encodedAttributes, [], `${name}: encoded placeholder or tooltip`)
      const errors = await page.locator('.error-banner:visible').allTextContents()
      assert.deepEqual(errors, [], `${name}: ${errors.join('; ')}`)
      const file = path.join(artifacts, `${name}.png`)
      await page.screenshot({ path: file, fullPage: true })
      report.screenshots.push(path.basename(file)); report.pages.push(name)
    }
    await page.goto(`${base}/config`)
    await page.locator('.app-shell').waitFor()
    assert.equal(await page.locator('.app-shell').evaluate(node => node.__vue__.$options._base.version), '2.6.14')
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
    await page.locator('input[type=number]').first().fill('4')
    await page.locator('.sidebar a').filter({ hasText: '人工策划' }).click()
    await page.getByRole('heading', { name: '离开策划配置？', exact: true }).waitFor()
    await page.getByRole('button', { name: '继续编辑', exact: true }).click()
    assert.equal(new URL(page.url()).pathname, '/config')
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
    assert.equal(await page.getByPlaceholder('输入完整选题 ID', { exact: true }).getAttribute('type'), 'text')
    await page.getByPlaceholder('输入选题标题关键词', { exact: true }).waitFor()
    await shot('manual-topics')
    await page.getByRole('button', { name: '保存', exact: true }).click()
    await page.getByRole('button', { name: '下一步', exact: true }).click()
    await page.getByRole('button', { name: '提交人工策划', exact: true }).waitFor()
    await shot('manual-confirm')

    await page.goto(`${base}/manual`)
    await page.getByRole('button', { name: '新建人工策划', exact: true }).click()
    await page.locator('.manual-create-meta input[type=text]').fill('Vue2营销数量验证')
    await page.locator('.manual-create-meta select').selectOption('marketing')
    await page.getByRole('button', { name: '下一步', exact: true }).click()
    await page.locator('.manual-topic-filters select').first().selectOption('non_marketing')
    await page.getByRole('button', { name: '查询', exact: true }).click()
    await page.locator('.manual-topic-table tbody input').first().check()
    await page.getByPlaceholder('请输入生成内容数量').fill('12')
    await shot('manual-marketing-topic')
    await page.getByRole('button', { name: '保存', exact: true }).click()
    await page.getByRole('button', { name: '下一步', exact: true }).click()
    assert.match(await page.locator('.manual-review-total').innerText(), /12/)
    await shot('manual-marketing-confirm')

    await page.goto(`${base}/results`)
    await page.getByRole('button', { name: '查看策划', exact: true }).first().waitFor()
    await shot('results-accounts')
    await page.getByRole('button', { name: '导出报表', exact: true }).click()
    await page.locator('.export-dates input').nth(0).fill('2026-11-01')
    await page.locator('.export-dates input').nth(1).fill('2026-11-30')
    await page.route('**/api/query/export', route => route.fulfill({
      status: 422, contentType: 'application/json', body: JSON.stringify({ detail: '导出范围校验失败，请调整日期' }),
    }))
    await page.getByRole('button', { name: '确认导出', exact: true }).click()
    await page.getByText('导出范围校验失败，请调整日期', { exact: true }).waitFor()
    await shot('results-export-error')
    await page.unroute('**/api/query/export')
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: '确认导出', exact: true }).click(),
    ])
    assert.match(download.suggestedFilename(), /\.xlsx$/)
    assert.equal(await download.failure(), null)
    const exportBytes = fs.readFileSync(await download.path())
    assert.equal(exportBytes.subarray(0, 2).toString(), 'PK')
    await page.locator('.export-dialog').waitFor({ state: 'hidden' })
    await shot('results-export-success')
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
    const tasks = await (await page.request.post(`${base}/api/query/manual-tasks`, { data: { page: 1, page_size: 10, filters: {} } })).json()
    const batch = tasks.items.find(task => task.batch_id).batch_id
    await page.goto(`${base}/results?batch=${batch}`)
    await page.locator('.planning-dashboard').waitFor()
    await page.locator('.planning-expand-btn').first().click()
    await page.getByRole('button', { name: '查看计划详情：选题T2', exact: true }).waitFor()
    await shot('results-batch-detail')
    await page.getByRole('button', { name: '查看计划详情：选题T2', exact: true }).click()
    await page.getByRole('dialog').waitFor()
    await shot('results-plan-detail')
    await page.goto(`${base}/auto`)
    await page.getByRole('button', { name: '查看策划', exact: true }).first().waitFor()
    assert.equal(new URL(page.url()).pathname, '/results')
    await shot('legacy-auto-redirect')
    for (const width of [1280, 1920]) {
      await page.setViewportSize({ width, height: 900 })
      await page.goto(`${base}/config`)
      await page.getByRole('button', { name: '编辑配置', exact: true }).waitFor()
      await shot(`config-width-${width}`)
    }
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
