import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { serverOptions } from './tooling/serverOptions'

export default defineConfig(({ command }) => {
  // Building static browser assets needs no credentials or running database.
  if (command === 'build') return { plugins: [vue()] }
  // Project scripts inject MySQL's public settings; standalone npm uses local defaults.
  const options = serverOptions(process.env)
  return {
    plugins: [vue()],
    server: options,
    preview: options,
  }
})

