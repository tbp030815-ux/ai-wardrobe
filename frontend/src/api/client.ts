import type { Clothes, Model, Outfit, Recommendation, TryOnResult } from '../types'

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

export async function fetchRecommendation(
  location: string,
  occasion: string,
): Promise<Recommendation> {
  // URLSearchParams 自动做百分号编码，中文城市名不用手动 encodeURIComponent
  const params = new URLSearchParams({ location, occasion })
  return request<Recommendation>(`/api/recommendation?${params}`)
}

export async function fetchModels(): Promise<Model[]> {
  return request<Model[]>('/api/models')
}

export async function uploadModel(file: File): Promise<Model> {
  const form = new FormData()
  form.append('file', file)
  return request<Model>('/api/model', { method: 'POST', body: form })
}

export async function setDefaultModel(modelId: number): Promise<Model> {
  return request<Model>(`/api/models/${modelId}/default`, { method: 'PUT' })
}

/** 一次调用 = 一张图。批量对比由调用方串行发起，见 pages/TryOn.tsx */
export async function generateTryOn(
  clothesIds: number[],
  modelId?: number,
): Promise<TryOnResult> {
  const body: { clothes_ids: number[]; model_id?: number } = { clothes_ids: clothesIds }
  // 不传 model_id 时省掉这个键：显式传 undefined 会序列化成 null，后端会当成「指定了 null 模特」
  if (modelId !== undefined) body.model_id = modelId

  return request<TryOnResult>('/api/tryon', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function fetchOutfits(limit?: number): Promise<Outfit[]> {
  // 结果图以 MB 计，历史列表必须有上限；不传就让后端用自己的默认值
  const query = limit === undefined ? '' : `?limit=${limit}`
  return request<Outfit[]>(`/api/outfits${query}`)
}

/* 三个删除端点都会删掉磁盘上的图片文件，且**返回被删的那一行 JSON**：
   request() 一律 response.json()，后端要是回 204 空响应体，这里会解析失败。 */

export async function deleteClothes(clothesId: number): Promise<Clothes> {
  return request<Clothes>(`/api/clothes/${clothesId}`, { method: 'DELETE' })
}

export async function deleteModel(modelId: number): Promise<Model> {
  return request<Model>(`/api/models/${modelId}`, { method: 'DELETE' })
}

export async function deleteOutfit(outfitId: number): Promise<Outfit> {
  return request<Outfit>(`/api/outfits/${outfitId}`, { method: 'DELETE' })
}
