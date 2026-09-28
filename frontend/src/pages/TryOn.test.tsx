// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import type { Clothes, Model, TryOnResult } from '../types'
import * as client from '../api/client'
import TryOn from './TryOn'

vi.mock('../api/client')

function clothes(id: number, sub: string, role: string): Clothes {
  return {
    id,
    user_id: 1,
    image_path: `/uploads/${id}.jpg`,
    cropped_path: `/uploads/${id}_cropped.png`,
    category: role,
    sub_category: sub,
    color: null,
    style: null,
    season: null,
    tags: null,
    created_at: '2026-09-25 10:00:00',
    role,
  }
}

const topA = clothes(1, '白色T恤', '上衣')
const topB = clothes(2, '蓝色衬衫', '上衣')
const pants = clothes(3, '牛仔裤', '下装')

const model: Model = {
  id: 1,
  user_id: 1,
  image_path: '/uploads/m1.jpg',
  height_cm: null,
  body_type: null,
  is_default: true,
  created_at: '2026-09-25 10:00:00',
}

const otherModel: Model = { ...model, id: 2, image_path: '/uploads/m2.jpg', is_default: false }

function outfit(id: number, clothesIds: number[]): TryOnResult {
  return {
    id,
    user_id: 1,
    model_id: 1,
    clothes_ids: clothesIds,
    generated_by: 'doubao-seedream-4-0-250828',
    result_image_url: `/uploads/tryon/${id}.jpg`,
    created_at: '2026-09-25 10:05:00',
    warnings: [],
  }
}

const GENERATE = '生成试穿'
const COMPARE = /^对比生成（(\d+) 张）$/

function renderTryOn(entry = '/tryon') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <TryOn />
    </MemoryRouter>,
  )
}

async function renderLoaded(entry = '/tryon') {
  const view = renderTryOn(entry)
  await screen.findByText('牛仔裤') // 衣物列表到齐
  return view
}

beforeEach(() => {
  vi.mocked(client.fetchWardrobe).mockResolvedValue([topA, topB, pants])
  vi.mocked(client.fetchModels).mockResolvedValue([model])
  vi.mocked(client.fetchOutfits).mockResolvedValue([])
  // 每个 mock 都要有默认实现：漏一个就会返回 undefined，
  // 而 clearAllMocks 只清调用记录、不清实现，漏掉的实现会泄漏到下一个用例
  vi.mocked(client.generateTryOn).mockResolvedValue(outfit(100, [1]))
  vi.mocked(client.uploadModel).mockResolvedValue(model)
  vi.mocked(client.deleteModel).mockResolvedValue(model)
  vi.mocked(client.deleteOutfit).mockResolvedValue(outfit(1, []))
  // 删除一律先弹确认框；不 stub 的话 jsdom 的 window.confirm 返回 undefined（等同取消）
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('TryOn 加载', () => {
  it('renders the wardrobe items to choose from', async () => {
    await renderLoaded()

    expect(screen.getByText('白色T恤')).toBeTruthy()
    expect(screen.getByText('蓝色衬衫')).toBeTruthy()
    expect(screen.getByText('牛仔裤')).toBeTruthy()
  })

  it('shows an empty hint when the wardrobe has nothing in it', async () => {
    vi.mocked(client.fetchWardrobe).mockResolvedValue([])

    renderTryOn()

    expect(await screen.findByText('衣柜还是空的，先去添加衣物')).toBeTruthy()
  })

  it('shows the result history', async () => {
    vi.mocked(client.fetchOutfits).mockResolvedValue([outfit(7, [1, 3])])

    await renderLoaded()

    expect(await screen.findByAltText('试穿结果 7')).toBeTruthy()
  })

  it('tells the user that the arm pose may drift', async () => {
    // 两轮 prompt 调优共 19 次真实调用都没挡住，只能写进产品文案
    await renderLoaded()

    expect(screen.getByText(/手臂姿势可能与原图有差异/)).toBeTruthy()
  })

  it('names occlusion as the trigger instead of "changing a top"', async () => {
    // 实测触发条件是「参考衣物与手臂区域重叠」而非「换上衣」——
    // 手臂搭在胯上挡住裤子时，只换裤子一样会漂。
    // 成因写错会让用户在不匹配的场景里误判，也会让下一个人继续往错的方向调 prompt。
    await renderLoaded()

    expect(screen.getByText(/参考衣物与手臂区域重叠时/)).toBeTruthy()
  })
})

describe('TryOn 模特', () => {
  it('marks the default model and uses it for generation', async () => {
    await renderLoaded()

    expect(screen.getByLabelText('模特 1').getAttribute('aria-pressed')).toBe('true')

    fireEvent.click(screen.getByLabelText('选择 上衣 1'))
    fireEvent.click(screen.getByRole('button', { name: GENERATE }))

    await waitFor(() => expect(client.generateTryOn).toHaveBeenCalledWith([1], 1))
  })

  it('switches to another model when one is clicked', async () => {
    vi.mocked(client.fetchModels).mockResolvedValue([model, otherModel])
    await renderLoaded()

    fireEvent.click(screen.getByLabelText('模特 2'))
    fireEvent.click(screen.getByLabelText('选择 上衣 1'))
    fireEvent.click(screen.getByRole('button', { name: GENERATE }))

    await waitFor(() => expect(client.generateTryOn).toHaveBeenCalledWith([1], 2))
  })

  it('blocks generation until a model photo exists', async () => {
    vi.mocked(client.fetchModels).mockResolvedValue([])
    await renderLoaded()

    fireEvent.click(screen.getByLabelText('选择 上衣 1'))

    expect(screen.getByText('请先上传一张模特全身照')).toBeTruthy()
    expect(screen.getByRole('button', { name: GENERATE })).toHaveProperty('disabled', true)
  })

  it('uploads a model photo and shows it in the list', async () => {
    vi.mocked(client.fetchModels).mockResolvedValue([])
    vi.mocked(client.uploadModel).mockResolvedValue(model)
    const { container } = await renderLoaded()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['x'], 'me.jpg')] } })

    await waitFor(() => expect(client.uploadModel).toHaveBeenCalled())
    expect(await screen.findByLabelText('模特 1')).toBeTruthy()
  })
})

describe('TryOn 生成试穿', () => {
  it('keeps the button disabled until something is selected', async () => {
    await renderLoaded()

    expect(screen.getByRole('button', { name: GENERATE })).toHaveProperty('disabled', true)

    fireEvent.click(screen.getByLabelText('选择 上衣 1'))

    expect(screen.getByRole('button', { name: GENERATE })).toHaveProperty('disabled', false)
  })

  it('sends every selected id in one request and renders the result', async () => {
    vi.mocked(client.generateTryOn).mockResolvedValue(outfit(101, [1, 3]))
    await renderLoaded()

    fireEvent.click(screen.getByLabelText('选择 上衣 1'))
    fireEvent.click(screen.getByLabelText('选择 下装 3'))
    fireEvent.click(screen.getByRole('button', { name: GENERATE }))

    await waitFor(() => expect(client.generateTryOn).toHaveBeenCalledTimes(1))
    expect(client.generateTryOn).toHaveBeenCalledWith([1, 3], 1)
    expect(await screen.findByAltText('试穿结果 101')).toBeTruthy()
  })

  it('shows the warnings that came back with the result', async () => {
    vi.mocked(client.generateTryOn).mockResolvedValue({
      ...outfit(101, [1]),
      warnings: ['衣物 1 的参考图分辨率过低（40×40），试穿保真度可能较差'],
    })
    await renderLoaded()

    fireEvent.click(screen.getByLabelText('选择 上衣 1'))
    fireEvent.click(screen.getByRole('button', { name: GENERATE }))

    expect(await screen.findByText(/衣物 1 的参考图分辨率过低/)).toBeTruthy()
  })

  it('shows the server message on failure and keeps the selection', async () => {
    vi.mocked(client.generateTryOn).mockRejectedValue(
      new Error('图像生成服务不可用：额度已用完'),
    )
    await renderLoaded()

    fireEvent.click(screen.getByLabelText('选择 上衣 1'))
    fireEvent.click(screen.getByRole('button', { name: GENERATE }))

    expect(await screen.findByText('图像生成服务不可用：额度已用完')).toBeTruthy()
    expect(screen.getByLabelText('选择 上衣 1')).toHaveProperty('checked', true)
  })

  it('disables both buttons while a generation is in flight', async () => {
    // StrictMode 下 effect 双跑，生成只能挂在 click handler 上；再叠一道防重复提交
    vi.mocked(client.generateTryOn).mockReturnValue(new Promise(() => {}))
    await renderLoaded()

    fireEvent.click(screen.getByLabelText('选择 上衣 1'))
    fireEvent.click(screen.getByRole('button', { name: GENERATE }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: GENERATE })).toHaveProperty('disabled', true),
    )
    expect(client.generateTryOn).toHaveBeenCalledTimes(1)
  })

  it('counts the seconds spent waiting', async () => {
    // 静态 spinner 等 60 秒看着像卡死
    vi.mocked(client.generateTryOn).mockReturnValue(new Promise(() => {}))
    await renderLoaded()
    fireEvent.click(screen.getByLabelText('选择 上衣 1'))

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: GENERATE }))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })

    expect(screen.getByText(/已等待 3 秒/)).toBeTruthy()
    vi.useRealTimers()
  })
})

describe('TryOn 对比生成', () => {
  it('offers no compare button when every role has a single item', async () => {
    await renderLoaded()

    fireEvent.click(screen.getByLabelText('选择 上衣 1'))
    fireEvent.click(screen.getByLabelText('选择 下装 3'))

    expect(screen.queryByRole('button', { name: COMPARE })).toBeNull()
  })

  it('labels the compare button with the variant count', async () => {
    await renderLoaded()

    fireEvent.click(screen.getByLabelText('选择 上衣 1'))
    fireEvent.click(screen.getByLabelText('选择 上衣 2'))

    expect(screen.getByRole('button', { name: '对比生成（2 张）' })).toBeTruthy()
  })

  it('generates one image per variant, one item per role, serially', async () => {
    vi.mocked(client.generateTryOn)
      .mockResolvedValueOnce(outfit(101, [1, 3]))
      .mockResolvedValueOnce(outfit(102, [2, 3]))
    await renderLoaded()

    fireEvent.click(screen.getByLabelText('选择 上衣 1'))
    fireEvent.click(screen.getByLabelText('选择 上衣 2'))
    fireEvent.click(screen.getByLabelText('选择 下装 3'))
    fireEvent.click(screen.getByRole('button', { name: '对比生成（2 张）' }))

    await waitFor(() => expect(client.generateTryOn).toHaveBeenCalledTimes(2))
    expect(client.generateTryOn).toHaveBeenNthCalledWith(1, [1, 3], 1)
    expect(client.generateTryOn).toHaveBeenNthCalledWith(2, [2, 3], 1)
    expect(await screen.findByAltText('试穿结果 101')).toBeTruthy()
    expect(await screen.findByAltText('试穿结果 102')).toBeTruthy()
  })

  it('keeps the successes when one variant fails', async () => {
    vi.mocked(client.generateTryOn)
      .mockResolvedValueOnce(outfit(101, [1, 3]))
      .mockRejectedValueOnce(new Error('生成请求过于频繁，请稍后重试'))
    await renderLoaded()

    fireEvent.click(screen.getByLabelText('选择 上衣 1'))
    fireEvent.click(screen.getByLabelText('选择 上衣 2'))
    fireEvent.click(screen.getByRole('button', { name: '对比生成（2 张）' }))

    expect(await screen.findByAltText('试穿结果 101')).toBeTruthy()
    expect(
      await screen.findByText('第 2 组失败：生成请求过于频繁，请稍后重试'),
    ).toBeTruthy()
  })
})

describe('TryOn 从推荐页带过来的预选', () => {
  it('pre-selects the ids in the query param', async () => {
    await renderLoaded('/tryon?ids=1,3')

    expect(screen.getByLabelText('选择 上衣 1')).toHaveProperty('checked', true)
    expect(screen.getByLabelText('选择 下装 3')).toHaveProperty('checked', true)
    expect(screen.getByLabelText('选择 上衣 2')).toHaveProperty('checked', false)
  })

  it('drops ids that are no longer in the wardrobe', async () => {
    // 链接会比衣物活得久
    await renderLoaded('/tryon?ids=1,999')

    expect(screen.getByLabelText('选择 上衣 1')).toHaveProperty('checked', true)
    expect(client.generateTryOn).not.toHaveBeenCalled()
  })

  it('ignores a malformed param instead of breaking the page', async () => {
    await renderLoaded('/tryon?ids=abc,,1')

    expect(screen.getByLabelText('选择 上衣 1')).toHaveProperty('checked', true)
  })
})

describe('TryOn 历史记录', () => {
  it('re-selects the items of a past outfit', async () => {
    vi.mocked(client.fetchOutfits).mockResolvedValue([outfit(7, [2, 3])])
    await renderLoaded()

    fireEvent.click(await screen.findByRole('button', { name: '改用这几件' }))

    expect(screen.getByLabelText('选择 上衣 2')).toHaveProperty('checked', true)
    expect(screen.getByLabelText('选择 下装 3')).toHaveProperty('checked', true)
  })
})

describe('TryOn 删除模特照', () => {
  it('asks before deleting and does nothing when the user cancels', async () => {
    await renderLoaded()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)

    fireEvent.click(screen.getByLabelText('删除模特 1'))

    expect(confirm).toHaveBeenCalled()
    expect(client.deleteModel).not.toHaveBeenCalled()
    expect(screen.getByLabelText('模特 1')).toBeTruthy()
  })

  it('deletes the model and follows the server when the default is promoted', async () => {
    // 删掉的正是默认模特：补位由服务端在同一事务里做，前端重新拉一次而不是自己算，
    // 否则「默认」徽标和下次试穿用的模特会对不上
    vi.mocked(client.fetchModels)
      .mockResolvedValueOnce([model, otherModel])
      .mockResolvedValueOnce([{ ...otherModel, is_default: true }])
    await renderLoaded()

    fireEvent.click(screen.getByLabelText('删除模特 1'))

    await waitFor(() => expect(client.deleteModel).toHaveBeenCalledWith(1))
    expect(screen.queryByLabelText('模特 1')).toBeNull()
    expect(screen.getByLabelText('模特 2').getAttribute('aria-pressed')).toBe('true')
  })

  it('keeps the model and shows the server message when deletion fails', async () => {
    vi.mocked(client.deleteModel).mockRejectedValue(new Error('模特不存在'))
    await renderLoaded()

    fireEvent.click(screen.getByLabelText('删除模特 1'))

    expect(await screen.findByText('模特不存在')).toBeTruthy()
    expect(screen.getByLabelText('模特 1')).toBeTruthy()
  })

  it('keeps the currently chosen model when another one is deleted', async () => {
    const third: Model = { ...model, id: 3, image_path: '/uploads/m3.jpg', is_default: false }
    vi.mocked(client.fetchModels)
      .mockResolvedValueOnce([model, otherModel, third])
      .mockResolvedValueOnce([model, third]) // 删掉的是 2 号，用户挑的 3 号还在
    await renderLoaded()
    fireEvent.click(screen.getByLabelText('模特 3')) // 用户显式选了第三张

    fireEvent.click(screen.getByLabelText('删除模特 2'))

    await waitFor(() => expect(client.deleteModel).toHaveBeenCalledWith(2))
    expect(screen.queryByLabelText('模特 2')).toBeNull()
    expect(screen.getByLabelText('模特 3').getAttribute('aria-pressed')).toBe('true')
  })
})

describe('TryOn 删除试穿结果', () => {
  it('asks before deleting and does nothing when the user cancels', async () => {
    vi.mocked(client.fetchOutfits).mockResolvedValue([outfit(7, [1])])
    await renderLoaded()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)

    fireEvent.click(screen.getByLabelText('删除试穿结果 7'))

    expect(confirm).toHaveBeenCalled()
    expect(client.deleteOutfit).not.toHaveBeenCalled()
    expect(screen.getByAltText('试穿结果 7')).toBeTruthy()
  })

  it('removes only the deleted result', async () => {
    // 结果图是按 MB 计的，这条路径是结果图持续累积的解药
    vi.mocked(client.fetchOutfits).mockResolvedValue([outfit(7, [1]), outfit(8, [3])])
    await renderLoaded()

    fireEvent.click(screen.getByLabelText('删除试穿结果 7'))

    await waitFor(() => expect(client.deleteOutfit).toHaveBeenCalledWith(7))
    await waitFor(() => expect(screen.queryByAltText('试穿结果 7')).toBeNull())
    expect(screen.getByAltText('试穿结果 8')).toBeTruthy()
  })

  it('keeps the result and shows the server message when deletion fails', async () => {
    vi.mocked(client.fetchOutfits).mockResolvedValue([outfit(7, [1])])
    vi.mocked(client.deleteOutfit).mockRejectedValue(new Error('试穿记录不存在'))
    await renderLoaded()

    fireEvent.click(screen.getByLabelText('删除试穿结果 7'))

    expect(await screen.findByText('试穿记录不存在')).toBeTruthy()
    expect(screen.getByAltText('试穿结果 7')).toBeTruthy()
  })
})

describe('TryOn 上限', () => {
  it('refuses to select more items than the backend accepts', async () => {
    const many = [1, 2, 3, 4, 5, 6, 7, 8, 9].map((id) => clothes(id, `上衣${id}`, '上衣'))
    vi.mocked(client.fetchWardrobe).mockResolvedValue(many)
    renderTryOn()
    await screen.findByText('上衣1')

    for (const id of many.map((item) => item.id)) {
      fireEvent.click(screen.getByLabelText(`选择 上衣 ${id}`))
    }

    expect(screen.getByText('一次最多试穿 8 件衣物')).toBeTruthy()
    expect(screen.getByLabelText('选择 上衣 9')).toHaveProperty('checked', false)
  })
})
