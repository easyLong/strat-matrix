const fs = require('node:fs')
const path = require('node:path')
const babel = require('@babel/core')
const Vue = require('vue')
const compiler = require('vue-template-compiler')
const templateCompiler = require('vue-template-babel-compiler')
Vue.config.productionTip = false
Vue.config.devtools = false
const root = path.resolve(__dirname, '../../src')
const cache = new Map()

function load(file) {
  if (!path.extname(file)) file += '.js'
  file = path.resolve(file)
  if (cache.has(file)) return cache.get(file).exports
  const module = { exports: {} }
  cache.set(file, module)
  if (file.endsWith('.json')) {
    module.exports = JSON.parse(fs.readFileSync(file, 'utf8'))
    return module.exports
  }
  let source = fs.readFileSync(file, 'utf8')
  let descriptor
  if (file.endsWith('.vue')) {
    descriptor = compiler.parseComponent(source)
    source = descriptor.script.content
  }
  const compiled = babel.transformSync(source, {
    configFile: false, babelrc: false,
    plugins: [require('@babel/plugin-transform-modules-commonjs')],
  }).code
  const localRequire = name => {
    if (name.startsWith('@/')) return load(path.join(root, name.slice(2)))
    if (name.startsWith('.')) return load(path.resolve(path.dirname(file), name))
    return require(name)
  }
  new Function('require', 'module', 'exports', compiled)(localRequire, module, module.exports)
  if (descriptor) {
    const template = compiler.compile(descriptor.template.content)
    if (template.errors.length) throw new Error(template.errors.join('\n'))
    const compiledRender = templateCompiler(`var render = function () {${template.render}}; var staticRenderFns = [${template.staticRenderFns.map(body => `function () {${body}}`).join(',')}];`)
    Object.assign(module.exports.default, new Function(`${compiledRender}; return { render, staticRenderFns }`)())
  }
  return module.exports
}

Vue.component('BodyPortal', load(path.join(root, 'components/BodyPortal.vue')).default)
module.exports = { load, Vue }
