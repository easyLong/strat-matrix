const { it: test } = require('mocha')
const assert = require('node:assert/strict')
const path = require('node:path')
const { load } = require('./helpers/vue2-loader.cjs')
const transport = load(path.resolve(__dirname,'../src/api/http.ts'))
const { api } = load(path.resolve(__dirname,'../src/api.ts'))

test('old running Java remains usable while a new query contract is staged', async () => {
  const calls=[]
  transport.setPlanningHttp({request:async config=>{calls.push(config);return {data:{service:'ok',database:'ok'},headers:{}}}})
  try {
    await api.health(); await api.accounts(20,true); await api.saveConfig({planning_days:[1]},3)
    assert.equal(calls[1].method,'GET')
    assert.equal(calls[1].url,'/accounts?limit=20&include_disabled=true')
    assert.equal(calls[2].method,'PUT')
    assert.equal(calls[2].url,'/config?expected_version=3')
  } finally { transport.setPlanningHttp() }
})
test('new Java advertises explicit POST queries and writes are never retried', async () => {
  const calls=[]
  transport.setPlanningHttp({request:async config=>{calls.push(config);return {data:{apiContract:'post-v1'},headers:{}}}})
  try {
    await api.health();await api.accounts(20);await api.saveConfig({planning_days:[1]},3)
    assert.equal(calls[1].method,'POST');assert.equal(calls[1].url,'/accounts/query')
    assert.equal(calls[2].url,'/config/save');assert.equal(JSON.parse(calls[2].data).expectedVersion,3)
    transport.setPlanningHttp({request:async config=>{calls.push(config);throw new Error('unavailable')}},{queryContract:'post-v1'})
    const before=calls.length
    await assert.rejects(api.saveConfig({},4))
    assert.equal(calls.length,before+1)
  } finally { transport.setPlanningHttp() }
})
test('a late health response cannot change another host binding contract', () => {
  transport.setPlanningHttp()
  const previous=transport.queryContractScope()
  transport.setPlanningHttp()
  transport.detectQueryContract('post-v1',previous)
  assert.equal(transport.usePostQueryContract(),false)
})
