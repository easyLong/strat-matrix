import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'
import { authorizePlanningRequest } from '../host/runtime'

export interface PlanningHttpClient { request(config: AxiosRequestConfig): Promise<any> }
export interface PlanningHttpOptions {
  apiPrefix?: string
  responseMode?: 'axios' | 'body'
  unwrapResponse?: (body: any) => any
  readError?: (error: unknown) => string | undefined
  onRequestError?: (error: PlanningRequestError) => void
}
export class PlanningRequestError extends Error {
  constructor(message: string, public status?: number, public retryAfter?: number) {
    super(message)
    this.name = 'PlanningRequestError'
  }
}
let development: AxiosInstance | undefined
const developmentHttp = () => development || (development = axios.create({ baseURL: '/api', timeout: 30000 }))
let transport: PlanningHttpClient | undefined
let settings: PlanningHttpOptions = {}
export function setPlanningHttp(client?: PlanningHttpClient, options: PlanningHttpOptions = {}) {
  const prefix = options.apiPrefix
  if (prefix && (!prefix.startsWith('/') || /[?#%\\]|\/\//.test(prefix) || prefix.split('/').some(p => p === '..' || p === '.')))
    throw new Error('Java策划接口前缀无效')
  transport = client
  settings = { ...options }
}

async function requestResponse<T>(path: string, options: RequestInit, responseType?: 'blob') {
  const method = (options.method || 'POST').toUpperCase()
  if (method !== 'POST' && !(method === 'GET' && path === '/health'))
    throw new PlanningRequestError('策划业务接口仅支持POST请求')
  authorizePlanningRequest(path, method)
  const policy = settings
  try {
    const headers: Record<string, string> = {}
    if (Array.isArray(options.headers)) {
      for (const [key, value] of options.headers) headers[key] = value
    } else if (options.headers && typeof (options.headers as Headers).forEach === 'function') {
      (options.headers as Headers).forEach((value, key) => { headers[key] = value })
    } else Object.assign(headers, options.headers)
    const result = await (transport || developmentHttp()).request({
      url: path, method, data: options.body,
      ...(policy.apiPrefix ? { baseURL: policy.apiPrefix } : {}),
      signal: options.signal || undefined,
      responseType,
      headers: {
        'Content-Type': 'application/json',
        ...(method === 'GET' ? { 'Cache-Control': 'no-cache, no-store' } : {}),
        ...headers,
      },
    })
    const response = policy.responseMode === 'body' ? { data: result, headers: {} } : result
    if (!response || !('data' in response)) throw new PlanningRequestError('宿主接口响应格式不匹配')
    if (responseType === 'blob') {
      if (typeof Blob === 'undefined' || !(response.data instanceof Blob)) throw new PlanningRequestError('导出接口未返回文件')
      return response as { data: T; headers: Record<string, any> }
    }
    return { ...response, data: policy.unwrapResponse ? policy.unwrapResponse(response.data) : response.data } as { data: T; headers: Record<string, any> }
  } catch (error) {
    if (axios.isCancel(error) || options.signal?.aborted) {
      const aborted = new Error('请求已取消')
      aborted.name = 'AbortError'
      throw aborted
    }
    let failure: PlanningRequestError
    if (error instanceof PlanningRequestError) failure = error
    else if (axios.isAxiosError(error) && error.response) {
      let body = error.response.data
      // Download errors arrive as Blob too; retain the server's validation message.
      if (typeof Blob !== 'undefined' && body instanceof Blob) {
        try { body = JSON.parse(await body.text()) } catch { body = undefined }
      }
      const delay = Number(error.response.headers?.['retry-after'])
      const status = error.response.status
      failure = new PlanningRequestError(policy.readError?.(error) || (typeof body?.detail === 'string' ? body.detail
        : status === 429 ? '服务繁忙，请稍后重试' : `请求失败（${status}）`), status,
        status === 429 && Number.isFinite(delay) && delay > 0 ? Math.min(120, Math.ceil(delay)) : undefined)
    } else {
      failure = new PlanningRequestError(policy.readError?.(error)
        || (axios.isAxiosError(error) && error.code === 'ECONNABORTED' ? '请求超时，请稍后重试' : '后端服务尚未连接'))
    }
    try { policy.onRequestError?.(failure) } catch { /* Keep the original failure if host reporting fails. */ }
    throw failure
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  return (await requestResponse<T>(path, options)).data
}

export function requestBlob(path: string, options: RequestInit = {}) {
  return requestResponse<Blob>(path, options, 'blob')
}
