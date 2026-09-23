import type { Clothes } from '../types'

const NETWORK_ERROR_MESSAGE = '无法连接后端服务，请确认后端已启动'

/** 把失败响应转成可读错误：优先用后端的 detail，否则用状态码兜底 */
async function toError(response: Response): Promise<Error> {
  try {
    const data = await response.json()
    if (data?.detail) return new Error(String(data.detail))
  } catch {
    // 响应体不是 JSON，走下面的兜底
  }
  return new Error(`请求失败（HTTP ${response.status}）`)
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch {
    throw new Error(NETWORK_ERROR_MESSAGE)
  }
  if (!response.ok) throw await toError(response)
  return response.json() as Promise<T>
}

export async function fetchWardrobe(): Promise<Clothes[]> {
  return request<Clothes[]>('/api/wardrobe')
}

export async function uploadClothes(file: File): Promise<Clothes> {
  const form = new FormData()
  form.append('file', file)
  return request<Clothes>('/api/upload', { method: 'POST', body: form })
}
