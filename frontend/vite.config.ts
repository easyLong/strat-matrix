import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', '')
  const backendPort = env.BACKEND_PORT || '6930'
  const frontendPort = Number(env.FRONTEND_PORT || '930')

  return {
    plugins: [vue()],
    server: {
      host: '127.0.0.1',
      port: frontendPort,
      proxy: {
        '/api': `http://127.0.0.1:${backendPort}`,
      },
    },
    preview: {
      host: '127.0.0.1',
      port: frontendPort,
      proxy: {
        '/api': `http://127.0.0.1:${backendPort}`,
      },
    },
  }
})

