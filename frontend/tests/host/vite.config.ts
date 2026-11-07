import { defineConfig } from 'vite'
import { createVuePlugin } from 'vite-plugin-vue2'
import path from 'node:path'
export default defineConfig({
  root: __dirname,
  plugins: [createVuePlugin()],
  resolve: { dedupe: ['vue'] },
  build: { outDir: path.resolve(__dirname, '../../../run/frontend-host-preview'), emptyOutDir: true },
})
