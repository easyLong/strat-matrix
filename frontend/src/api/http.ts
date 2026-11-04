import axios, { type AxiosInstance } from 'axios'

/** All page traffic stays on the Java API prefix; the host can inject its client. */
export const http = axios.create({ baseURL: '/api', timeout: 30000 })
let transport: AxiosInstance = http
export function setPlanningHttp(client: AxiosInstance = http) { transport = client }

async function requestResponse<T>(path: string, options: RequestInit, responseType?: 'blob') {
  try {
    const headers: Record<string, string> = {}
    if (Array.isArray(options.headers)) {
      for (const [key, value] of options.headers) headers[key] = value
    } else if (options.headers && typeof (options.headers as Headers).forEach === 'function') {
      (options.headers as Headers).forEach((value, key) => { headers[key] = value })
    } else Object.assign(headers, options.headers)
    const response = await transport.request<T>({
      url: path, method: options.method || 'GET', data: options.body,
      signal: options.signal || undefined,
      responseType,
      headers: {
        'Content-Type': 'application/json',
        ...(!options.method || options.method.toUpperCase() === 'GET' ? { 'Cache-Control': 'no-cache, no-store' } : {}),
        ...headers,
      },
    })
    return response
  } catch (error) {
    if (axios.isCancel(error) || options.signal?.aborted) {
      const aborted = new Error('请求已取消')
      aborted.name = 'AbortError'
      throw aborted
    }
    if (axios.isAxiosError(error) && error.response) {
      let body = error.response.data
      // Download errors arrive as Blob too; retain the server's validation message.
      if (typeof Blob !== 'undefined' && body instanceof Blob) {
        try { body = JSON.parse(await body.text()) } catch { body = undefined }
      }
      const detail = body?.detail
      throw new Error(typeof detail === 'string' ? detail : `请求失败（${error.response.status}）`)
    }
    throw new Error(axios.isAxiosError(error) && error.code === 'ECONNABORTED' ? '请求超时，请稍后重试' : '后端服务尚未连接')
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  return (await requestResponse<T>(path, options)).data
}

export function requestBlob(path: string, options: RequestInit = {}) {
  return requestResponse<Blob>(path, options, 'blob')
}
