import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { reviewRuntime } from './review-runtime.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dist = path.join(root, 'frontend', 'dist')
const outputDir = path.join(root, 'review-export')
const outputFile = path.join(outputDir, '多账号智能策划_最新版前端UI_离线评审.html')
const apiBase = process.env.REVIEW_API_BASE || 'http://127.0.0.1:6930/api'

async function getJson(endpoint) {
  const response = await fetch(`${apiBase}${endpoint}`, { signal: AbortSignal.timeout(30000) })
  if (!response.ok) throw new Error(`${endpoint} 返回 ${response.status}`)
  return response.json()
}

async function mapWithConcurrency(values, mapper, concurrency = 6) {
  const result = new Array(values.length)
  let next = 0
  await Promise.all(Array.from({ length: Math.min(concurrency, values.length) }, async () => {
    while (next < values.length) {
      const index = next++
      result[index] = await mapper(values[index])
    }
  }))
  return result
}

async function collectSnapshot() {
  const [health, config, configVersions, tags, accounts, activeAccounts, topics, batches, tasks, planningAccounts, planningCycles] = await Promise.all([
    getJson('/health'),
    getJson('/config'),
    getJson('/config/versions'),
    getJson('/tag-taxonomy'),
    getJson('/accounts?limit=1000&include_disabled=true'),
    getJson('/accounts?limit=1000&include_disabled=false'),
    getJson('/topics?limit=1000'),
    getJson('/batches?limit=5000'),
    getJson('/manual-plans/tasks'),
    getJson('/planning-accounts'),
    getJson('/planning-cycles'),
  ])

  const detailRows = await Promise.all(batches.map(async batch => [String(batch.id), await getJson(`/batches/${batch.id}`)]))
  const batchDetails = Object.fromEntries(detailRows)
  const accountItems = {}
  const cycleItems = {}
  for (const batch of Object.values(batchDetails)) {
    for (const item of batch.items || []) {
      const enriched = { ...item, batch_id: batch.id, batch_code: batch.batch_code, plan_type: batch.plan_type, cycle_start: batch.cycle_start, cycle_end: batch.cycle_end, batch_created_at: batch.created_at }
      const date = new Date(`${batch.cycle_start}T12:00:00Z`)
      date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7)
      const cycleId = date.toISOString().slice(0, 10)
      ;(cycleItems[cycleId] ||= []).push(enriched)
    }
  }
  // The account page uses the first history record for its lifecycle badge.
  // Preserve native response fields and ordering; flattening batches changes that badge.
  const accountIds = [...new Set([...accounts, ...planningAccounts].map(account => account.account_id))]
  const histories = await mapWithConcurrency(accountIds, async accountId => [accountId,
    await getJson(`/items?account=${encodeURIComponent(accountId)}&limit=5000`)])
  Object.assign(accountItems, Object.fromEntries(histories))
  const topicDetails = Object.fromEntries(await Promise.all(topics.map(async topic => [topic.topic_id, await getJson(`/topics/${encodeURIComponent(topic.topic_id)}/detail${topic.topic_type ? `?topic_type=${encodeURIComponent(topic.topic_type)}` : ''}`)])))
  const items = Object.values(batchDetails).flatMap(batch => batch.items)
  const adjustments = Object.fromEntries(await mapWithConcurrency(items, async item => [String(item.id),
    await getJson(`/items/${item.id}/adjustments`)]))
  const replacementCandidates = Object.fromEntries(await mapWithConcurrency(items.filter(item => item.allow_replace), async item => [String(item.id),
    await getJson(`/items/${item.id}/replacement-candidates`)]))
  const nativeCycles = await mapWithConcurrency(planningCycles, async cycle => [cycle.cycle_id,
    await getJson(`/planning-cycles/${encodeURIComponent(cycle.cycle_id)}/items?limit=5000`)])
  Object.assign(cycleItems, Object.fromEntries(nativeCycles))
  const manualDates = [...new Set(Object.values(batchDetails).filter(batch => batch.plan_type === 'manual').flatMap(batch => batch.items.map(item => item.publish_date)))]
  const accountAvailability = Object.fromEntries(await mapWithConcurrency(manualDates, async date => [date,
    await getJson(`/manual-plans/account-availability?publish_date=${date}`)]))

  return {
    health,
    config,
    configVersions,
    tags,
    accounts,
    activeAccounts,
    topics,
    batches,
    tasks,
    planningAccounts,
    planningCycles,
    batchDetails,
    cycleItems,
    accountItems,
    topicDetails,
    adjustments,
    replacementCandidates,
    accountAvailability,
    exportedAt: new Date().toISOString(),
  }
}

function js(value) {
  return JSON.stringify(value).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029')
}


async function main() {
  // Compile the real frontend every time, so a stale build cannot change the review UI.
  const frontend = path.join(root, 'frontend')
  if (process.platform === 'win32') execFileSync(process.env.ComSpec || 'cmd.exe', ['/d', '/c', 'npm run build'], { cwd: frontend, stdio: 'inherit' })
  else execFileSync('npm', ['run', 'build'], { cwd: frontend, stdio: 'inherit' })
  const snapshot = await collectSnapshot()
  const source = await fs.readFile(path.join(dist, 'index.html'), 'utf8')
  const cssMatch = source.match(/<link[^>]+href="(\/assets\/[^"]+\.css)"[^>]*>/)
  const jsMatch = source.match(/<script[^>]+src="([^"]+\.js)"[^>]*><\/script>/)
  if (!cssMatch || !jsMatch) throw new Error('未找到 Vite 生成的 CSS 或 JS 文件')
  const css = await fs.readFile(path.join(dist, cssMatch[1].replace(/^\//, '')), 'utf8')
  const jsBundle = await fs.readFile(path.join(dist, jsMatch[1].replace(/^\//, '')), 'utf8')
  let fonts = await fs.readFile(path.join(dist, 'fonts/misans/misans.css'), 'utf8')
  for (const match of [...fonts.matchAll(/url\(["']?(\.\/[^"')]+)["']?\)/g)]) {
    const data = await fs.readFile(path.join(dist, 'fonts/misans', match[1]))
    fonts = fonts.replace(match[0], `url("data:font/woff2;base64,${data.toString('base64')}")`)
  }
  const metadata = { commit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
    frontendTree: execFileSync('git', ['rev-parse', 'HEAD:frontend'], { cwd: root, encoding: 'utf8' }).trim(),
    builtAt: new Date().toISOString(), cssAsset: cssMatch[1], jsAsset: jsMatch[1], accountHistorySource: 'native-account-items-api' }
  const title = '多账号智能策划 · 最新版前端UI离线评审'
  const html = source
    .replace(/<link[^>]+href="\/assets\/[^\"]+\.css"[^>]*>/, () => `<style>${css}</style>`)
    .replace(/<script[^>]+src="[^"]+\.js"[^>]*><\/script>/, () => `<script>globalThis.__STRAT_MATRIX_REVIEW_BUILD__=${js(metadata)};(${reviewRuntime.toString()})(${js(snapshot)});</script><script type="module">${jsBundle.replace(/<\/script/gi, '<\\/script')}</script>`)
    .replace(/<link[^>]+href="\/fonts\/misans\/misans\.css"[^>]*>/, () => `<style>${fonts}</style>`)
    .replace(/<title>[^<]*<\/title>/, `<title>${title}</title>`)
  await fs.mkdir(outputDir, { recursive: true })
  await fs.writeFile(outputFile, html, 'utf8')
  await fs.writeFile(path.join(outputDir, '多账号智能策划_最新版UI_全页面核查版.html'), html, 'utf8')
  // Correct the file delivered previously as well, so the existing link shows the current UI.
  await fs.writeFile(path.join(outputDir, '多账号智能策划_交互评审原型.html'), html, 'utf8')
  await fs.writeFile(path.join(outputDir, '多账号智能策划_前端评审原型_20261020.html'), html, 'utf8')
  const stat = await fs.stat(outputFile)
  console.log(JSON.stringify({ outputFile, bytes: stat.size, ...metadata, accounts: snapshot.accounts.length, topics: snapshot.topics.length, batches: snapshot.batches.length }, null, 2))
}

main().catch(error => { console.error(error.stack || error.message); process.exitCode = 1 })
