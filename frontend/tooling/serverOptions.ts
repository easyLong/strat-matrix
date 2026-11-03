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
  // Both modes use Java. A missing Java service must never silently bypass it.
  const target = settings.JAVA_GATEWAY_URL || (mode === 'local_development' ? 'http://127.0.0.1:6931' : '')
  if (!target) throw new Error('Java业务服务地址尚未配置')
  const address = new URL(target)
  if (!['http:', 'https:'].includes(address.protocol) || address.username || address.password
      || address.pathname !== '/' || address.search || address.hash) throw new Error('接口代理地址必须为无凭据的HTTP服务根地址')
  const proxy = { target: address.origin, rewrite: (path: string) => `/api/plan${path.slice('/api'.length)}` }
  return { host: settings.FRONTEND_HOST || '0.0.0.0', port: frontendPort, proxy: { '/api': proxy } }
}
