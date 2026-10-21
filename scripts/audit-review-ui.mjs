import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createHash } from 'node:crypto'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const debuggerBase = process.env.REVIEW_DEBUGGER || 'http://127.0.0.1:9355'
const liveBase = process.env.REVIEW_FRONTEND || 'http://127.0.0.1:930'
const apiBase = process.env.REVIEW_API_BASE || 'http://127.0.0.1:6930/api'
const html = path.join(root, 'review-export/多账号智能策划_最新版前端UI_离线评审.html')
const checks = [], issues = []
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
const normalize = value => Array.isArray(value) ? value.map(normalize) : value && typeof value === 'object'
  ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => [k, normalize(v)])) : value
const digest = value => createHash('sha256').update(JSON.stringify(normalize(value))).digest('hex')
const record = (name, success, detail = '') => {
  const entry = { name, success, detail }
  checks.push(entry); if (!success) issues.push(entry)
  console.log(`${success ? 'PASS' : 'FAIL'} ${name}${detail ? ': ' + detail : ''}`)
}
async function get(endpoint) {
  const r = await fetch(apiBase + endpoint)
  return { status: r.status, data: await r.json() }
}
async function browser(offline) {
  const target = await (await fetch(debuggerBase + '/json/new?about:blank', { method: 'PUT' })).json()
  const socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject })
  let seq = 0
  const pending = new Map(), errors = [], httpRequests = [], writes = []
  socket.onmessage = event => {
    const m = JSON.parse(event.data)
    if (m.id) { const p = pending.get(m.id); if (p) { pending.delete(m.id); m.error ? p.reject(m.error) : p.resolve(m.result) } }
    if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails)
    if (m.method === 'Network.requestWillBeSent' && /^https?:/.test(m.params.request.url)) httpRequests.push(m.params.request.url)
    if (m.method === 'Fetch.requestPaused') {
      const request = m.params.request
      // UI comparisons never write to the real backend, including accidentally clicked submit buttons.
      if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method)) {
        writes.push({ url: request.url, method: request.method })
        void send('Fetch.fulfillRequest', { requestId: m.params.requestId, responseCode: 403,
          body: Buffer.from(JSON.stringify({ detail: 'Audit blocked a real backend mutation' })).toString('base64') })
      } else void send('Fetch.continueRequest', { requestId: m.params.requestId })
    }
  }
  function send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++seq
      pending.set(id, { resolve, reject })
      socket.send(JSON.stringify({ id, method, params }))
    })
  }
  async function evaluate(expression) {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text)
    return r.result?.value
  }
  async function settle() {
    await send('Page.bringToFront')
    for (let i = 0; i < 70; i++) {
      const ready = await evaluate(`Boolean(document.querySelector('.main') && !document.querySelector('.loading-skeleton,[class*="-leave-active"],[class*="-enter-active"]') && !/正在读取|正在连接服务/.test((document.querySelector('.main')?.innerText || '')+[...document.querySelectorAll('.drawer')].map(el=>el.innerText).join(' ')))`)
      if (ready) break
      await delay(100)
    }
    await evaluate('document.fonts.ready.then(()=>true)')
    await delay(120)
  }
  async function route(value) {
    // Hash navigation can retain an old component's filters; start each case in a fresh document.
    await send('Page.navigate', { url: 'about:blank' })
    for(let i=0;i<30;i++){if(await evaluate('location.href === "about:blank"'))break;await delay(30)}
    await send('Page.navigate', { url: offline ? pathToFileURL(html).href + '#' + value : liveBase + value })
    await delay(250); await settle()
  }
  async function click(selector) {
    await send('Page.bringToFront')
    await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)throw Error('Missing selector: '+${JSON.stringify(selector)});el.scrollIntoView({block:'center',behavior:'instant'});el.click()})()`)
    await delay(80); await settle()
  }
  async function button(text, scope = 'body') {
    await send('Page.bringToFront')
    await evaluate(`(()=>{const root=document.querySelector(${JSON.stringify(scope)});const b=[...root.querySelectorAll('button')].find(el=>el.textContent.trim()===${JSON.stringify(text)}&&!el.disabled);if(!b)throw Error('Missing button: '+${JSON.stringify(text)});b.scrollIntoView({block:'center',behavior:'instant'});b.click()})()`)
    await delay(80); await settle()
  }
  async function fill(selector, value) {
    await send('Page.bringToFront')
    await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)throw Error('Missing input: '+${JSON.stringify(selector)});el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}))})()`)
    await delay(80)
  }
  async function upload(selector, filename) {
    const { root: doc } = await send('DOM.getDocument')
    const { nodeId } = await send('DOM.querySelector', { nodeId: doc.nodeId, selector })
    await send('DOM.setFileInputFiles', { nodeId, files: [filename] })
    await delay(150); await settle()
  }
  await send('Runtime.enable'); await send('Page.enable'); await send('Network.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  if (offline) await send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 })
  else await send('Fetch.enable', { patterns: [{ urlPattern: '*://*/api/*', requestStage: 'Request' }] })
  return { send, evaluate, route, click, button, fill, upload, settle, errors, httpRequests, writes,
    async close() { socket.close(); await fetch(debuggerBase + '/json/close/' + target.id) } }
}
const signature = `(()=>{
  const roots=[document.querySelector('.main'),...document.querySelectorAll('.drawer-mask,.app-confirm-mask,.taxonomy-action-popover,.cascader-popup')].filter(Boolean);
  const visible=el=>Boolean(el.getClientRects().length && getComputedStyle(el).visibility!=='hidden');
  return {
    text:roots.map(el=>el.innerText.replace(/\\s+/g,' ').trim()),
    controls:roots.flatMap(root=>[...root.querySelectorAll('input,select,textarea,button')].filter(visible).map(el=>[el.tagName,el.type,el.getAttribute('placeholder')||'',el.getAttribute('aria-label')||'',el.value,el.checked,el.disabled,el.getAttribute('aria-expanded')])),
    geometry:roots.flatMap(root=>[...root.querySelectorAll('.card-head,.planning-dashboard,.planning-account-head,.planning-plan-card,.manual-stepper,.manual-topic-selection-layout,.taxonomy-group,.drawer-head,.detail-filter-fields,.account-pagination,th')].filter(visible).map(el=>{const r=el.getBoundingClientRect();return [el.className,...[r.x+scrollX,r.y+scrollY,r.width,r.height].map(n=>Math.round(n*10)/10)]}))
  }
})()`

async function main() {
  let live, offline
  try {
    live = await browser(false); offline = await browser(true)
    await live.route('/config'); await offline.route('/config')
    const snapshot = await offline.evaluate('window.__STRAT_MATRIX_REVIEW__.snapshot')
    const both = async (method, ...args) => { await live[method](...args); await offline[method](...args) }
    async function compare(name) {
      await delay(50)
      const a = await live.evaluate(signature), b = await offline.evaluate(signature)
      const diffs = ['text', 'controls', 'geometry'].filter(k => digest(a[k]) !== digest(b[k]))
      if (diffs.length) await fs.writeFile(path.join(root, '.tmp-ui-audit-diff.json'), JSON.stringify({ name, diffs, live: a, offline: b }, null, 2))
      record(name, !diffs.length, diffs.join(', '))
    }
    await compare('AI策划配置：默认只读总览')
    for (const dimension of ['T1 业务属性', 'T2 经营作用', 'T3 内容主题', 'T4 目标客群', 'T5 使用场景']) {
      await both('button', dimension); await compare('标签配置：' + dimension)
    }
    await both('button', '编辑配置'); await compare('配置编辑：表单、生命周期、经营目标')
    await both('button', 'T3 内容主题'); await both('click', '.taxonomy-pill:not(:disabled)'); await compare('标签编辑：改名与停用菜单')
    await both('button', '改名', '.taxonomy-action-popover'); await compare('标签编辑：改名输入框')
    await both('fill', 'input[aria-label="修改名称"]', '评审临时名称'); await both('button', '确认改名'); await compare('标签编辑：改名后展示（未保存）')
    await both('button', '取消编辑'); await compare('取消编辑确认弹窗')
    await both('button', '继续编辑', '.app-confirm'); await compare('取消编辑：继续编辑')
    await both('button', '取消编辑'); await both('button', '确认取消', '.app-confirm'); await compare('取消编辑：恢复原配置')
    await both('button', '历史配置'); await compare('历史配置列表')
    await both('button', '查看详情'); await compare('历史配置：版本摘要与完整详情')
    await both('click', '.drawer-head .icon-btn'); await both('button', '恢复此版本'); await compare('历史配置：恢复确认弹窗')
    await both('click', '.app-confirm-mask'); await both('button', '返回配置')

    await both('route', '/manual'); await compare('人工策划：策划任务列表')
    await both('button', '新建人工策划'); await compare('新建人工策划：创建策划')
    await both('fill', 'input[placeholder="请输入任务名称"]', '全页面评审'); await both('fill', 'input[type=date]', '2026-11-02'); await both('button', '下一步'); await compare('人工策划：选择账号及筛选维度')
    await both('fill', 'input[placeholder="请输入计划账号数量"]', '3'); await both('button', '查询'); await compare('人工策划：点击查询并选中账号')
    await both('button', '下一页', '.manual-account-pagination'); await compare('账号选择：分页'); await both('button', '上一页', '.manual-account-pagination')
    await both('button', '模板导入'); await compare('账号选择：模板导入面板')
    const csv = path.join(root, '.tmp-review-accounts.csv')
    await fs.writeFile(csv, '\uFEFFUM号\r\n'+snapshot.accounts.slice(0,3).map(a=>a.um_no).join('\r\n')+'\r\nUNKNOWN-UM\r\n')
    await both('upload', '.manual-file-input', csv); await compare('模板导入：识别、勾选与未匹配UM号')
    await both('button', '筛选选择'); await both('button', '查询')
    await both('button', '保存'); await compare('账号选择：保存后冻结与下一步')
    await both('button', '下一步'); await compare('人工策划：选择选题默认列表')
    await both('click', '.topic-filters-toggle button'); await compare('选择选题：筛选项展开')
    await both('fill', 'input[placeholder="输入选题标题关键词"]', '周末'); await both('button', '查询'); await compare('选择选题：标题查询结果')
    await both('click', '.manual-topic-table input[type=checkbox]'); await compare('选择选题：勾选加入左侧')
    await both('button', '保存'); await compare('选择选题：保存确认'); await both('button', '下一步'); await compare('人工策划：提交概览两栏')
    // Do not submit on the live frontend: it would create a real preview/task.

    await both('route', '/results'); await compare('策划结果：账号视图默认列表')
    await both('button', '筛选条件'); await compare('账号视图：筛选项展开')
    await both('fill', 'input[placeholder="输入账号 ID 或昵称"]', '旅行'); await both('button', '查询'); await compare('账号视图：查询结果')
    await both('fill', 'input[placeholder="输入账号 ID 或昵称"]', '不存在的账号'); await both('button', '查询'); await compare('账号视图：无结果空状态')
    await both('route', '/results'); await both('button', '下一页'); await compare('账号视图：账号列表分页')
    await both('route', '/results?dimension=period'); await compare('策划结果：周期视图默认列表')
    await both('button', '筛选条件'); await compare('周期视图：年月周筛选')
    await both('button', '查看批次'); await compare('周期视图：展开批次列表')
    for (const route of ['/results?dimension=account&account=DEMO-P-B', '/results?dimension=period&cycle=2026-10-19', '/results?dimension=period&batch=108', '/results?dimension=period&batch=108&plan_type=manual&from=manual']) {
      await both('route', route); await compare('策划详情：' + route.split('?')[1])
      if (!route.includes('account=')) await both('click', '.planning-expand-btn')
      await compare('详情周历展开：' + route.split('?')[1])
      await both('button', '筛选条件'); await compare('详情筛选展开：' + route.split('?')[1])
      await both('click', '.planning-plan-card'); await compare('单条计划详情：' + route.split('?')[1]); await both('click', '.drawer-head .icon-btn')
      if(route.includes('cycle=')){await both('button','下一页','.planning-detail-card');await compare('周期策划详情：账号分页')}
    }
    const replaceable = Object.values(snapshot.batchDetails).flatMap(b => b.items).find(i => i.allow_replace)
    const parent = Object.values(snapshot.batchDetails).find(b => b.items.some(i => i.id === replaceable.id))
    await both('route', '/results?dimension=account&account=' + replaceable.account_id)
    // Select the exact slot through its visible topic title and date; preserve the actual Vue click handler.
    const openSlot = `(()=>{const title=${JSON.stringify(replaceable.topic_title)};const cards=[...document.querySelectorAll('.planning-plan-card')];const c=cards.find(el=>el.querySelector('b')?.textContent===title&&el.querySelector('.planning-plan-batch')?.textContent===${JSON.stringify(parent.batch_code)}&&el.closest('.planning-day')?.querySelector('header b')?.textContent===${JSON.stringify(replaceable.publish_date.slice(5))});if(!c)throw Error('Missing replaceable plan');c.scrollIntoView({block:'center'});c.click()})()`
    await both('evaluate', openSlot); await both('settle');
    if (await live.evaluate("[...document.querySelectorAll('.drawer button')].some(b=>b.textContent.trim()==='替换选题')")) {
      await both('button', '替换选题', '.drawer'); await compare('替换选题：候选列表与调整记录')
      await both('button', '筛选条件', '.drawer'); await compare('替换选题：筛选维度')
      await both('click', '.topic-check input[type=radio]'); await compare('替换选题：选中候选选题')
      await both('click', '.drawer-head .icon-btn')
    } else record('替换选题入口', false, '目标卡片未定位到可替换的槽位')

    // Compare every exported read response, not only the first account used in screenshots.
    const endpoints = ['/health','/config','/config/versions','/tag-taxonomy','/accounts?limit=1000&include_disabled=true','/accounts?limit=1000&include_disabled=false','/topics?limit=1000','/batches?limit=200','/batches?limit=5000','/batches?limit=5000&plan_type=auto','/batches?limit=5000&plan_type=manual','/planning-accounts','/planning-cycles','/manual-plans/tasks',
      ...snapshot.accounts.map(a=>'/items?account='+encodeURIComponent(a.account_id)+'&limit=5000'),
      ...snapshot.batches.map(b=>'/batches/'+b.id),
      ...snapshot.planningCycles.map(c=>'/planning-cycles/'+c.cycle_id+'/items?limit=5000'),
      ...Object.keys(snapshot.replacementCandidates || {}).map(id=>'/items/'+id+'/replacement-candidates'),
      ...Object.entries(snapshot.adjustments).filter(([,records])=>records.length).map(([id])=>'/items/'+id+'/adjustments'),
      ...Object.keys(snapshot.accountAvailability||{}).map(d=>'/manual-plans/account-availability?publish_date='+d)]
    const apiDiffs = []
    for (const endpoint of endpoints) {
      const expected = await get(endpoint)
      const actual = await offline.evaluate(`fetch('/api'+${JSON.stringify(endpoint)}).then(async r=>({status:r.status,data:await r.json()}))`)
      if (digest(expected) !== digest(actual)) apiDiffs.push(endpoint)
    }
    record('全部已导出GET接口数据、排序与候选范围', !apiDiffs.length, `${endpoints.length} 个请求${apiDiffs.length ? '；差异：' + apiDiffs.join(', ') : ''}`)

    await live.send('Emulation.setDeviceMetricsOverride',{width:1280,height:900,deviceScaleFactor:1,mobile:false})
    await offline.send('Emulation.setDeviceMetricsOverride',{width:1280,height:900,deviceScaleFactor:1,mobile:false})
    for(const route of ['/config','/manual','/results','/results?dimension=period','/results?account=DEMO-P-B','/results?batch=108']){
      await both('route',route);await compare('1280桌面布局：'+route)
    }

    await offline.route('/config')
    const writes = await offline.evaluate(`(async()=>{
      const request=async(p,body,method='POST')=>{const r=await fetch('/api'+p,{method,body:JSON.stringify(body)});return {status:r.status,data:await r.json()}};
      const s=window.__STRAT_MATRIX_REVIEW__.snapshot;
      const config={...s.config.config,hotspot_ratio:23};const v=s.config.version;
      const saved=await request('/config?expected_version='+v,config,'PUT');
      const stale=await request('/config?expected_version='+v,config,'PUT');
      const restored=await request('/config/versions/'+(saved.data.version-1)+'/restore?expected_version='+saved.data.version,{});
      const accounts=s.activeAccounts.filter(a=>a.marketing_eligible).slice(0,2), topics=s.topics.filter(t=>!t.is_marketing).slice(0,3);
      const preview=await request('/manual-plans/previews',{task_name:'离线全流程审查',publish_date:'2026-11-02',account_ids:accounts.map(a=>a.account_id),target_count:2,topic_ids:topics.map(t=>t.topic_id)});
      const task=await request('/manual-plans/previews/'+preview.data.preview_id+'/submit',{});
      const pendingAvailability=await fetch('/api/manual-plans/account-availability?publish_date=2026-11-02').then(r=>r.json());
      await new Promise(r=>setTimeout(r,1900));
      const done=s.tasks.find(t=>t.id===task.data.id), batch=s.batchDetails[done.batch_id];
      const available=await fetch('/api/manual-plans/account-availability?publish_date=2026-11-02').then(r=>r.json());
      const duplicate=await request('/manual-plans/previews',{task_name:'重复校验',publish_date:'2026-11-02',account_ids:accounts.map(a=>a.account_id),target_count:2,topic_ids:topics.map(t=>t.topic_id)});
      const group='review-group',leaf='review-leaf',tags=JSON.parse(JSON.stringify(s.tags.items));tags.T3.push({id:null,client_id:group,name:'评审分类',node_type:'group',enabled:true,parent_id:null},{id:null,client_id:leaf,name:'评审标签',node_type:'tag',enabled:true,parent_id:group});
      const tagResult=await request('/tag-taxonomy',{items:tags,expected_version:s.tags.version},'PUT');
      const savedGroup=tagResult.data.items.T3.find(t=>t.client_id===group),savedLeaf=tagResult.data.items.T3.find(t=>t.client_id===leaf);
      const cycle=s.planningCycles.find(c=>c.cycle_id==='2026-11-02');
      return {save:saved.status,stale:stale.status,restore:restored.status,previewCount:preview.data.items.length,pendingAvailability:pendingAvailability.planned_account_ids.length,taskDone:done.planning_status,slots:batch.items.length,availability:available.planned_account_ids.length,duplicate:duplicate.status,owner:s.planningAccounts.find(a=>a.account_id===accounts[0].account_id).account_owner,expectedOwner:accounts[0].organization,tagHierarchy:Boolean(savedGroup?.id&&savedLeaf?.id&&savedLeaf.parent_id===savedGroup.id),cycleCount:cycle?.content_count};
    })()`)
    record('离线写操作：配置保存、冲突、恢复', writes.save===200&&writes.stale===409&&writes.restore===200)
    record('人工策划：每账号一条分配与异步完成', writes.previewCount===2&&writes.slots===2&&writes.taskDone==='已完成')
    record('人工策划：完成前不占用、完成后置灰、防重复', writes.pendingAvailability===0&&writes.availability===2&&writes.duplicate>=400)
    record('人工策划：账号属主组织回填', writes.owner===writes.expectedOwner)
    record('人工策划：新增周期汇总同步', writes.cycleCount===2)
    record('新增标签：保存后分类与叶子关系保留', writes.tagHierarchy)
    record('全程没有修改真实后端', live.writes.length===0, JSON.stringify(live.writes))
    record('离线版没有HTTP网络请求', offline.httpRequests.length===0)
    record('所有页面无JavaScript异常', live.errors.length===0&&offline.errors.length===0)
    await fs.writeFile(path.join(root,'review-export/页面核查结果.json'),JSON.stringify({checkedAt:new Date().toISOString(),checks,issues},null,2))
    if(issues.length)process.exitCode=1
  } finally { if(live)await live.close();if(offline)await offline.close() }
}
main().catch(async error=>{console.error(error);process.exitCode=1;await fs.writeFile(path.join(root,'review-export/页面核查结果.json'),JSON.stringify({checks,issues,error:error.message},null,2))})
