/** Non-secret launcher inputs only. Standalone Vue development needs no Python or database. */
export function serverOptions(settings = {}) {
    const legacy = settings.JAVA_ACCESS_MODE || 'local_development';
    if (settings.PLANNING_ENV === undefined && !['local_development', 'bank'].includes(legacy))
        throw new Error('未知的页面接口接入方式');
    const mode = settings.PLANNING_ENV ?? (legacy === 'bank' ? 'inside' : 'outside');
    if (!['outside', 'inside'].includes(mode))
        throw new Error('PLANNING_ENV必须为outside或inside');
    const port = (value, fallback) => {
        const parsed = value === undefined || value === '' ? fallback : Number(value);
        if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535)
            throw new Error('服务端口必须在1到65535之间');
        return parsed;
    };
    const frontendPort = port(settings.FRONTEND_PORT, 930);
    // Both modes use Java. A missing Java service must never silently bypass it.
    const target = settings.JAVA_GATEWAY_URL || (mode === 'outside' ? 'http://127.0.0.1:6931' : '');
    if (!target)
        throw new Error('Java业务服务地址尚未配置');
    const address = new URL(target);
    if (!['http:', 'https:'].includes(address.protocol) || address.username || address.password
        || address.pathname !== '/' || address.search || address.hash)
        throw new Error('接口代理地址必须为无凭据的HTTP服务根地址');
    const proxy = { target: address.origin, rewrite: (path) => `/api/plan${path.slice('/api'.length)}` };
    return { host: settings.FRONTEND_HOST || '0.0.0.0', port: frontendPort, proxy: { '/api': proxy } };
}
