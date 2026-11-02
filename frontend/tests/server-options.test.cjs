const assert = require('node:assert/strict')
const { test } = require('node:test')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const moduleUnderTest = { exports: {} }
const code = ts.transpileModule(fs.readFileSync(path.resolve(__dirname, '../tooling/serverOptions.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText
new Function('module', 'exports', code)(moduleUnderTest, moduleUnderTest.exports)
const { serverOptions } = moduleUnderTest.exports

test('standalone frontend uses local development defaults without a backend config reader', () => {
  assert.deepEqual(serverOptions(), { host: '0.0.0.0', port: 930, proxy: { '/api': 'http://127.0.0.1:6930' } })
})

test('bank frontend requires Java and cannot silently fall back to Python', () => {
  assert.throws(() => serverOptions({ JAVA_ACCESS_MODE: 'bank' }), /Java/)
  assert.throws(() => serverOptions({ JAVA_ACCESS_MODE: 'unknown' }))
  assert.throws(() => serverOptions({ JAVA_ACCESS_MODE: 'bank', JAVA_GATEWAY_URL: 'https://secret:token@bank.test' }))
  assert.throws(() => serverOptions({ JAVA_ACCESS_MODE: 'bank', JAVA_GATEWAY_URL: 'https://bank.test/?token=secret' }))
  const proxy = serverOptions({ JAVA_ACCESS_MODE: 'bank', JAVA_GATEWAY_URL: 'https://bank.test' }).proxy['/api']
  assert.equal(proxy.target, 'https://bank.test')
  assert.equal(proxy.rewrite('/api/config'), '/api/plan/config')
  assert.equal(proxy.rewrite('/api/query/export?name=%E4%B8%AD%E6%96%87&x=1&x=2'), '/api/plan/query/export?name=%E4%B8%AD%E6%96%87&x=1&x=2')
})

test('launcher-provided ports and gateway settings apply without exposing other environment values', () => {
  const options = serverOptions({ FRONTEND_PORT: '1930', BACKEND_PORT: '16930', BACKEND_HOST: '::', MYSQL_PASSWORD: 'not-public' })
  assert.equal(options.port, 1930)
  assert.equal(options.proxy['/api'], 'http://127.0.0.1:16930')
  assert.equal(JSON.stringify(options).includes('not-public'), false)
  assert.throws(() => serverOptions({ FRONTEND_PORT: '70000' }))
})
