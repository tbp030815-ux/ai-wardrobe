import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Clothes, Model, Outfit, Recommendation } from '../types'
import {
  deleteClothes,
  deleteModel,
  deleteOutfit,
  fetchAuthStatus,
  fetchModels,
  fetchOutfits,
  fetchRecommendation,
  fetchWardrobe,
  generateTryOn,
  login,
  logout,
  setDefaultModel,
  setUnauthorizedHandler,
  uploadClothes,
  uploadModel,
} from './client'

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
  // 未授权回调是模块级全局状态，不重置会跨用例泄漏
  setUnauthorizedHandler(null)
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

describe('fetchRecommendation', () => {
  const sampleRecommendation: Recommendation = {
    weather: {
      city: '上海',
      temperature: 28.8,
      apparent_temperature: 30.8,
      description: '晴间多云',
      temp_max: 31.0,
      temp_min: 23.5,
      precipitation_probability: 14,
      weather_code: 1,
      reference_temperature: 31,
    },
    occasion: '通勤',
    source: 'llm',
    reason: '清爽通勤装',
    items: [],
    gaps: [],
  }

  it('GETs /api/recommendation with encoded location and occasion params', async () => {
    const spy = stubFetch(async () => jsonResponse(sampleRecommendation))

    const result = await fetchRecommendation('上海', '通勤')

    expect(result).toEqual(sampleRecommendation)
    const url = new URL(spy.mock.calls[0][0], 'http://localhost')
    expect(url.pathname).toBe('/api/recommendation')
    expect(url.searchParams.get('location')).toBe('上海')
    expect(url.searchParams.get('occasion')).toBe('通勤')
    expect(spy.mock.calls[0][1]?.method).toBeUndefined() // 默认 GET，不是 POST
  })

  it('surfaces the server message when the city is not found', async () => {
    stubFetch(async () => jsonResponse({ detail: '没有找到城市「火星」，请换个说法试试' }, 404))

    await expect(fetchRecommendation('火星', '休闲')).rejects.toThrow('没有找到城市「火星」')
  })
})

const sampleModel: Model = {
  id: 1,
  user_id: 1,
  image_path: '/uploads/m1.jpg',
  height_cm: null,
  body_type: null,
  is_default: true,
  created_at: '2026-09-25 10:00:00',
}

const sampleOutfit: Outfit = {
  id: 7,
  user_id: 1,
  model_id: 1,
  clothes_ids: [3, 4],
  generated_by: 'doubao-seedream-4-0-250828',
  result_image_url: '/uploads/tryon/abc.jpg',
  created_at: '2026-09-25 10:05:00',
}

describe('fetchModels', () => {
  it('returns the model list from GET /api/models', async () => {
    const spy = stubFetch(async () => jsonResponse([sampleModel]))

    const result = await fetchModels()

    expect(result).toEqual([sampleModel])
    expect(spy.mock.calls[0][0]).toBe('/api/models')
  })
})

describe('uploadModel', () => {
  it('POSTs the file to /api/model as multipart field "file"', async () => {
    const spy = stubFetch(async () => jsonResponse(sampleModel))
    const file = new File(['fake-bytes'], 'me.jpg', { type: 'image/jpeg' })

    const result = await uploadModel(file)

    expect(result).toEqual(sampleModel)
    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('/api/model')
    expect(init?.method).toBe('POST')
    const body = init?.body as FormData
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('file')).toBe(file)
  })

  it('surfaces the server message when the image is rejected', async () => {
    stubFetch(async () => jsonResponse({ detail: '无法识别的图片格式' }, 400))

    await expect(uploadModel(new File(['x'], 'bad.txt', { type: 'text/plain' }))).rejects
      .toThrow('无法识别的图片格式')
  })
})

describe('setDefaultModel', () => {
  it('PUTs to /api/models/{id}/default', async () => {
    const spy = stubFetch(async () => jsonResponse(sampleModel))

    const result = await setDefaultModel(1)

    expect(result).toEqual(sampleModel)
    expect(spy.mock.calls[0][0]).toBe('/api/models/1/default')
    expect(spy.mock.calls[0][1]?.method).toBe('PUT')
  })
})

describe('generateTryOn', () => {
  it('POSTs clothes_ids as JSON and omits model_id when not chosen', async () => {
    const spy = stubFetch(async () => jsonResponse({ ...sampleOutfit, warnings: [] }))

    const result = await generateTryOn([3, 4])

    expect(result.clothes_ids).toEqual([3, 4])
    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('/api/tryon')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual({ clothes_ids: [3, 4] })
  })

  it('includes model_id when one is chosen', async () => {
    const spy = stubFetch(async () => jsonResponse({ ...sampleOutfit, warnings: [] }))

    await generateTryOn([3], 2)

    expect(JSON.parse(spy.mock.calls[0][1]?.body as string)).toEqual({
      clothes_ids: [3],
      model_id: 2,
    })
  })

  it('carries warnings through so the page can show them', async () => {
    stubFetch(async () =>
      jsonResponse({ ...sampleOutfit, warnings: ['衣物 3 的参考图分辨率过低（40×40）'] }),
    )

    const result = await generateTryOn([3])

    expect(result.warnings).toEqual(['衣物 3 的参考图分辨率过低（40×40）'])
  })

  it('surfaces the server message when generation is unavailable', async () => {
    stubFetch(async () => jsonResponse({ detail: '图像生成服务不可用：额度已用完' }, 503))

    await expect(generateTryOn([3])).rejects.toThrow('图像生成服务不可用')
  })

  it('surfaces the server message when rate limited', async () => {
    stubFetch(async () => jsonResponse({ detail: '生成请求过于频繁，请稍后重试' }, 429))

    await expect(generateTryOn([3])).rejects.toThrow('生成请求过于频繁')
  })

  it('throws a readable error when the backend is unreachable', async () => {
    stubFetch(async () => {
      throw new TypeError('Failed to fetch')
    })

    await expect(generateTryOn([3])).rejects.toThrow('无法连接后端服务')
  })
})

describe('fetchOutfits', () => {
  it('GETs /api/outfits without a limit when none is given', async () => {
    const spy = stubFetch(async () => jsonResponse([sampleOutfit]))

    const result = await fetchOutfits()

    expect(result).toEqual([sampleOutfit])
    expect(spy.mock.calls[0][0]).toBe('/api/outfits')
  })

  it('passes limit as a query param', async () => {
    const spy = stubFetch(async () => jsonResponse([]))

    await fetchOutfits(5)

    expect(spy.mock.calls[0][0]).toBe('/api/outfits?limit=5')
  })
})

describe('deleteClothes', () => {
  it('DELETEs /api/clothes/{id}', async () => {
    const spy = stubFetch(async () => jsonResponse(sampleClothes))

    const result = await deleteClothes(3)

    expect(result).toEqual(sampleClothes)
    expect(spy.mock.calls[0][0]).toBe('/api/clothes/3')
    expect(spy.mock.calls[0][1]?.method).toBe('DELETE')
  })

  it('surfaces the server message when the item is already gone', async () => {
    // 后端返回 JSON 而不是 204：request() 一律 response.json()，空响应体会解析失败
    stubFetch(async () => jsonResponse({ detail: '衣物不存在' }, 404))

    await expect(deleteClothes(999)).rejects.toThrow('衣物不存在')
  })
})

describe('deleteModel', () => {
  it('DELETEs /api/models/{id}', async () => {
    const spy = stubFetch(async () => jsonResponse(sampleModel))

    const result = await deleteModel(1)

    expect(result).toEqual(sampleModel)
    expect(spy.mock.calls[0][0]).toBe('/api/models/1')
    expect(spy.mock.calls[0][1]?.method).toBe('DELETE')
  })

  it('surfaces the server message when the model is already gone', async () => {
    stubFetch(async () => jsonResponse({ detail: '模特不存在' }, 404))

    await expect(deleteModel(999)).rejects.toThrow('模特不存在')
  })
})

describe('deleteOutfit', () => {
  it('DELETEs /api/outfits/{id}', async () => {
    const spy = stubFetch(async () => jsonResponse(sampleOutfit))

    const result = await deleteOutfit(7)

    expect(result).toEqual(sampleOutfit)
    expect(spy.mock.calls[0][0]).toBe('/api/outfits/7')
    expect(spy.mock.calls[0][1]?.method).toBe('DELETE')
  })

  it('surfaces the server message when the result is already gone', async () => {
    stubFetch(async () => jsonResponse({ detail: '试穿记录不存在' }, 404))

    await expect(deleteOutfit(999)).rejects.toThrow('试穿记录不存在')
  })
})

describe('认证', () => {
  it('POSTs the password to /api/auth/login as JSON', async () => {
    const spy = stubFetch(async () => jsonResponse({ authenticated: true }))

    await login('hunter2')

    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('/api/auth/login')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual({ password: 'hunter2' })
  })

  it('surfaces the server message when the password is wrong', async () => {
    stubFetch(async () => jsonResponse({ detail: '密码错误' }, 401))

    await expect(login('wrong')).rejects.toThrow('密码错误')
  })

  it('does not treat a wrong password as an expired session', async () => {
    // 登录失败的 401 不是「会话失效」：通知 handler 会把登录页刚显示的错误冲掉
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    stubFetch(async () => jsonResponse({ detail: '密码错误' }, 401))

    await expect(login('wrong')).rejects.toThrow('密码错误')

    expect(handler).not.toHaveBeenCalled()
  })

  it('GETs the auth status from /api/auth/me', async () => {
    const spy = stubFetch(async () => jsonResponse({ authenticated: false, configured: true }))

    const status = await fetchAuthStatus()

    expect(status).toEqual({ authenticated: false, configured: true })
    expect(spy.mock.calls[0][0]).toBe('/api/auth/me')
  })

  it('POSTs to /api/auth/logout', async () => {
    const spy = stubFetch(async () => jsonResponse({ authenticated: false }))

    await logout()

    expect(spy.mock.calls[0][0]).toBe('/api/auth/logout')
    expect(spy.mock.calls[0][1]?.method).toBe('POST')
  })

  it('notifies the app and still throws when a business request is rejected', async () => {
    // 会话过期 / 密码被改：任何业务请求的 401 都该把用户送回登录页，但错误本身不能吞掉
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    stubFetch(async () => jsonResponse({ detail: '请先登录' }, 401))

    await expect(fetchWardrobe()).rejects.toThrow('请先登录')

    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('does not notify the handler for non-auth failures', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    stubFetch(async () => jsonResponse({ detail: '数据库错误' }, 500))

    await expect(fetchWardrobe()).rejects.toThrow('数据库错误')

    expect(handler).not.toHaveBeenCalled()
  })
})
