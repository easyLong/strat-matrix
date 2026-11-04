// Test-fixture cloning only. Browser code is tested in Chromium separately.
const { serialize, deserialize } = require('node:v8')
if (typeof global.structuredClone !== 'function') global.structuredClone = value => deserialize(serialize(value))
if (typeof global.Blob === 'undefined') global.Blob = require('node:buffer').Blob
