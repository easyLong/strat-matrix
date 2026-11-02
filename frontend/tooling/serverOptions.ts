/** Non-secret launcher inputs only. Standalone Vue development needs no Python or database. */
export function serverOptions(settings: Record<string, string | undefined> = {}) {
  const mode = settings.JAVA_ACCESS_MODE || 'local_development'
  if (!['local_development', 'bank'].includes(mode)) throw new Error('未知的页面接口接入方式')
  const port = (value: string | undefined, fallback: number) => {
    const parsed = value === undefined || value === '' ? fallback : Number(value)
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) throw new Error('服务端口必须在1到65535之间')
    return parsed
  }
  const frontendPort = port(settings.FRONTEND_PORT, 930)
  const backendPort = port(settings.BACKEND_PORT, 6930)
  const rawHost = settings.BACKEND_HOST || '127.0.0.1'
  const host = ['0.0.0.0', '::'].includes(rawHost) ? '127.0.0.1' : rawHost
  const backendHost = host.includes(':') && !host.startsWith('[') ? `[${host}]` : host
  const target = mode === 'bank' ? settings.JAVA_GATEWAY_URL : `http://${backendHost}:${backendPort}`
  if (!target) throw new Error('行内Java接入层尚未实现或未配置')
  const address = new URL(target)
  if (!['http:', 'https:'].includes(address.protocol) || address.username || address.password
      || address.pathname !== '/' || address.search || address.hash) throw new Error('接口代理地址必须为无凭据的HTTP服务根地址')
  const proxy = mode === 'bank'
    ? { target: address.origin, rewrite: (path: string) => `/api/plan${path.slice('/api'.length)}` }
    : address.origin
  return { host: settings.FRONTEND_HOST || '0.0.0.0', port: frontendPort, proxy: { '/api': proxy } }
}
