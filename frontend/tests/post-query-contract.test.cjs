const { it: test } = require('mocha')
const assert = require('node:assert/strict')
const path = require('node:path')
const { load } = require('./helpers/vue2-loader.cjs')
const transport = load(path.resolve(__dirname,'../src/api/http.js'))
const { api } = load(path.resolve(__dirname,'../src/api.js'))

test('business POST requests do not depend on health or protocol negotiation', async () => {
  const calls=[]
  transport.setPlanningHttp({request:async config=>{calls.push(config);return {data:{service:'ok',database:'ok'},headers:{}}}})
  try {
    await api.accounts(20,true)
    await api.health()
    await api.saveConfig({planning_days:[1]},3)
    assert.equal(calls[0].method,'POST')
    assert.equal(calls[0].url,'/accounts/query')
    assert.deepEqual(JSON.parse(calls[0].data),{limit:20,includeDisabled:true})
    assert.equal(calls[1].method,'GET')
    assert.equal(calls[1].url,'/health')
    assert.equal(calls[2].method,'POST')
    assert.equal(calls[2].url,'/config/save')
  } finally {transport.setPlanningHttp()}
})

test('an unavailable POST fails once without falling back to old routes or verbs', async () => {
  const calls=[]
  transport.setPlanningHttp({request:async config=>{calls.push(config);throw new Error('unavailable')}})
  try {
    await assert.rejects(api.config())
    await assert.rejects(api.saveConfig({},4))
    assert.deepEqual(calls.map(({url,method})=>({url,method})),[
      {url:'/config/query',method:'POST'}, {url:'/config/save',method:'POST'},
    ])
  } finally {transport.setPlanningHttp()}
})

test('unsupported business GET and PUT are rejected before sending', async () => {
  let calls=0
  transport.setPlanningHttp({request:async () => { calls++;return {data:{},headers:{}} }})
  try {
    for (const [path,method] of [['/accounts','GET'],['/config','PUT'],['/config/query','GET']])
      await assert.rejects(transport.request(path,{method}),/仅支持POST/)
    assert.equal(calls,0)
  } finally {transport.setPlanningHttp()}
})

test('current page queries and saves use POST end to end without a compatibility mode', async () => {
  const calls=[]
  const topicId='选题 A/1'
  transport.setPlanningHttp({request:async config=>{
    calls.push(config)
    const value=/manual-plans\/(?:tasks|marketing-tasks)\/query$/.test(config.url) ? []
      : config.url.includes('tag-taxonomy') ? {version:1,items:{}} : {}
    return {data:value,headers:{}}
  }})
  try {
    await api.config();await api.configVersions();await api.saveConfig({},3);await api.restoreConfig(1,3)
    await api.tagTaxonomy();await api.saveTagTaxonomy({},1)
    await api.accounts(20,true);await api.manualAccountAvailability('2026-11-09')
    await api.topics();await api.topicDetail(topicId,'non_marketing')
    await api.batches('auto',10);await api.batch(88)
    await api.replacementCandidates(99);await api.adjustments(99)
    await api.manualTasks();await api.marketingTasks();await api.marketingTaskDetails('MAN-1')
    await api.manualTaskPage({page:1,page_size:20,filters:{}})
    await api.planPage({page:1,page_size:20,filters:{},mode:'account',account_id:'ACC-1'})
    await api.accountPage({page:1,page_size:20,filters:{}})
    await api.periodPage({page:1,page_size:20,filters:{}})
    await api.periodContext({cycle_start:'2026-11-09'})
    await api.resultFailures({page:1,page_size:20,filters:{},mode:'batch',batch_id:88})
    assert.equal(calls.length,23)
    for (const call of calls) {
      assert.equal(call.method,'POST',call.url)
      assert.ok(!call.url.includes('?'),call.url)
      assert.equal(typeof JSON.parse(call.data),'object',call.url)
    }
    const detail=calls.find(call=>call.url.includes('/detail/query'))
    assert.equal(detail.url,`/topics/${encodeURIComponent(topicId)}/detail/query`)
    assert.deepEqual(JSON.parse(detail.data),{topicType:'non_marketing'})
  } finally {transport.setPlanningHttp()}
})
