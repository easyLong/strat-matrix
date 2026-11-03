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
  const options = serverOptions()
  assert.equal(options.host, '0.0.0.0')
  assert.equal(options.port, 930)
  assert.equal(options.proxy['/api'].target, 'http://127.0.0.1:6931')
  assert.equal(options.proxy['/api'].rewrite('/api/config'), '/api/plan/config')
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
  assert.equal(options.proxy['/api'].target, 'http://127.0.0.1:6931')
  assert.equal(JSON.stringify(options).includes('not-public'), false)
  assert.throws(() => serverOptions({ FRONTEND_PORT: '70000' }))
})

test('local frontend uses configured Java without forwarding to Python on failure', () => {
  assert.equal(serverOptions({ JAVA_GATEWAY_URL: 'http://localhost:16931', BACKEND_PORT: '16930' }).proxy['/api'].target,
    'http://localhost:16931')
  assert.throws(() => serverOptions({ JAVA_GATEWAY_URL: 'http://localhost:6931/api' }))
})

test('outside and inside are the canonical selectors and take priority over legacy flags', () => {
  assert.equal(serverOptions({ PLANNING_ENV: 'outside', JAVA_ACCESS_MODE: 'bank' }).proxy['/api'].target, 'http://127.0.0.1:6931')
  assert.throws(() => serverOptions({ PLANNING_ENV: 'inside', JAVA_ACCESS_MODE: 'local_development' }), /Java/)
  assert.equal(serverOptions({ PLANNING_ENV: 'inside', JAVA_GATEWAY_URL: 'https://host.example' }).proxy['/api'].target, 'https://host.example')
  assert.throws(() => serverOptions({ PLANNING_ENV: 'invalid' }), /PLANNING_ENV/)
  assert.throws(() => serverOptions({ PLANNING_ENV: '' }), /PLANNING_ENV/)
})
