import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ command }) => {
  // Building static browser assets needs no credentials or running database.
  if (command === 'build') return { plugins: [vue()] }
  const backendDir = fileURLToPath(new URL('../backend/', import.meta.url))
  const venv = fileURLToPath(new URL(process.platform === 'win32'
    ? '../backend/.venv/Scripts/python.exe' : '../backend/.venv/bin/python', import.meta.url))
  const python = process.env.PYTHON_BIN || (existsSync(venv) ? venv
    : process.platform === 'win32' ? 'python' : 'python3')
  // This command returns only four non-secret bind/proxy settings.
  const settings = JSON.parse(execFileSync(python, ['-m', 'app.system_config', 'frontend-json'], {
    cwd: backendDir, encoding: 'utf8', timeout: 15000, windowsHide: true,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  })) as Record<string, string>
  const frontendHost = settings.FRONTEND_HOST
  const backendPort = settings.BACKEND_PORT
  const frontendPort = Number(settings.FRONTEND_PORT)

  return {
    plugins: [vue()],
    server: {
      host: frontendHost,
      port: frontendPort,
      proxy: {
        '/api': `http://127.0.0.1:${backendPort}`,
      },
    },
    preview: {
      host: frontendHost,
      port: frontendPort,
      proxy: {
        '/api': `http://127.0.0.1:${backendPort}`,
      },
    },
  }
})

