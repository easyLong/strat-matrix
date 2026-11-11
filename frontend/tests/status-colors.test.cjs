const { test } = require('mocha')
const assert = require('node:assert/strict')
const path = require('node:path')
const { load } = require('./helpers/vue2-loader.cjs')
const { statusTone } = load(path.resolve(__dirname, '../src/ui/status.js'))

test('running states use the brand color and waiting states keep warning semantics', () => {
  for (const status of ['进行中', '执行中', '处理中', '生产中', '生成中', '上传中'])
    assert.equal(statusTone(status), 'blue', status)
  for (const status of ['待定题', '待生产', '待生成', '未提交', '未完成', '热点空槽待填充'])
    assert.equal(statusTone(status), 'orange', status)
})

test('failed outcomes remain danger even when the label contains completion wording', () => {
  for (const status of ['生产失败', '生成失败', '部分失败', '已完成但存在异常'])
    assert.equal(statusTone(status), 'red', status)
  for (const status of ['已完成', '保存成功', '已连接'])
    assert.equal(statusTone(status), 'green', status)
  for (const status of ['状态未知', '无数据', '停用', '', null])
    assert.equal(statusTone(status), 'gray', status)
})
