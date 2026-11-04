const required = require('../package.json').engines.node
if (process.versions.node !== required) {
  console.error(`This frontend requires Node ${required}; current version is ${process.versions.node}. Switch Node before installing, testing, building or starting it.`)
  process.exit(1)
}
