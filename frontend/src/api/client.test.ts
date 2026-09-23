import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Clothes } from '../types'
import { fetchWardrobe, uploadClothes } from './client'

/** 替换全局 fetch，返回 spy 以便断言请求参数 */
function stubFetch(impl: (url: string, init?: RequestInit) => Promise<Response>) {
  const spy = vi.fn(impl)
  vi.stubGlobal('fetch', spy)
  return spy
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const sampleClothes: Clothes = {
  id: 1,
  user_id: 1,
  image_path: '/uploads/a.jpg',
  cropped_path: '/uploads/a_cropped.png',
  category: '上衣',
  sub_category: 'T恤',
  color: '藏青色',
  style: '休闲',
  season: '夏季',
  tags: null,
  created_at: '2026-09-22 10:00:00',
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchWardrobe', () => {
  it('returns the clothes list from GET /api/wardrobe', async () => {
    const spy = stubFetch(async () => jsonResponse([sampleClothes]))

    const result = await fetchWardrobe()

    expect(result).toEqual([sampleClothes])
    expect(spy.mock.calls[0][0]).toBe('/api/wardrobe')
  })

  it('throws with the server detail when the request fails', async () => {
    stubFetch(async () => jsonResponse({ detail: '数据库错误' }, 500))

    await expect(fetchWardrobe()).rejects.toThrow('数据库错误')
  })

  it('throws a readable error when the backend is unreachable', async () => {
    stubFetch(async () => {
      throw new TypeError('Failed to fetch')
    })

    await expect(fetchWardrobe()).rejects.toThrow('无法连接后端服务')
  })
})

describe('uploadClothes', () => {
  it('POSTs the file to /api/upload as multipart field "file"', async () => {
    const spy = stubFetch(async () => jsonResponse(sampleClothes))
    const file = new File(['fake-bytes'], 'shirt.jpg', { type: 'image/jpeg' })

    const result = await uploadClothes(file)

    expect(result).toEqual(sampleClothes)
    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('/api/upload')
    expect(init?.method).toBe('POST')
    const body = init?.body as FormData
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('file')).toBe(file)
  })

  it('surfaces the server message when the image is rejected', async () => {
    stubFetch(async () => jsonResponse({ detail: '无法识别的图片格式' }, 400))

    await expect(
      uploadClothes(new File(['not-an-image'], 'bad.txt', { type: 'text/plain' })),
    ).rejects.toThrow('无法识别的图片格式')
  })

  it('throws a readable error when the backend is unreachable', async () => {
    stubFetch(async () => {
      throw new TypeError('Failed to fetch')
    })

    await expect(
      uploadClothes(new File(['x'], 'a.jpg', { type: 'image/jpeg' })),
    ).rejects.toThrow('无法连接后端服务')
  })
})
