// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Clothes } from '../types'
import * as client from '../api/client'
import Wardrobe from './Wardrobe'

vi.mock('../api/client')

const shirt: Clothes = {
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

const EMPTY_HINT = '暂无衣物，点击右上角添加'
const UPLOAD_INPUT = '选择衣物照片'

function makeFile() {
  return new File(['bytes'], 'shirt.jpg', { type: 'image/jpeg' })
}

async function renderLoaded(items: Clothes[] = []) {
  vi.mocked(client.fetchWardrobe).mockResolvedValue(items)
  render(<Wardrobe />)
  await screen.findByText(items.length ? items[0].sub_category! : EMPTY_HINT)
}

beforeEach(() => {
  vi.mocked(client.fetchWardrobe).mockResolvedValue([])
  vi.mocked(client.uploadClothes).mockReset()
  vi.mocked(client.deleteClothes).mockResolvedValue(shirt)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

afterEach(() => {
  cleanup() // vitest 未开 globals，testing-library 不会自动清理 DOM
  vi.clearAllMocks()
})

describe('Wardrobe', () => {
  it('renders the clothes returned by the API', async () => {
    vi.mocked(client.fetchWardrobe).mockResolvedValue([shirt])

    render(<Wardrobe />)

    expect(await screen.findByText('T恤')).toBeTruthy()
    expect(screen.getByText('藏青色')).toBeTruthy()
    expect(screen.getByAltText('上衣')).toBeTruthy()
  })

  it('shows an empty hint when there are no clothes', async () => {
    render(<Wardrobe />)

    expect(await screen.findByText(EMPTY_HINT)).toBeTruthy()
  })

  it('shows the fetch error when the wardrobe cannot be loaded', async () => {
    vi.mocked(client.fetchWardrobe).mockRejectedValue(new Error('无法连接后端服务，请确认后端已启动'))

    render(<Wardrobe />)

    expect(await screen.findByText('无法连接后端服务，请确认后端已启动')).toBeTruthy()
  })

  it('shows a loading hint while the upload is in progress', async () => {
    let resolveUpload: (value: Clothes) => void = () => {}
    vi.mocked(client.uploadClothes).mockReturnValue(
      new Promise<Clothes>((resolve) => {
        resolveUpload = resolve
      }),
    )
    await renderLoaded()

    fireEvent.change(screen.getByLabelText(UPLOAD_INPUT), { target: { files: [makeFile()] } })

    expect(await screen.findByText('AI 正在抠图识别…')).toBeTruthy()

    resolveUpload(shirt)
    expect(await screen.findByText('T恤')).toBeTruthy()
  })

  it('uploads the chosen file and adds the new item to the list', async () => {
    vi.mocked(client.uploadClothes).mockResolvedValue(shirt)
    await renderLoaded()
    const file = makeFile()

    fireEvent.change(screen.getByLabelText(UPLOAD_INPUT), { target: { files: [file] } })

    expect(await screen.findByText('T恤')).toBeTruthy()
    expect(client.uploadClothes).toHaveBeenCalledWith(file)
    expect(screen.queryByText(EMPTY_HINT)).toBeNull()
  })

  it('shows the server message when the upload is rejected', async () => {
    vi.mocked(client.uploadClothes).mockRejectedValue(new Error('无法识别的图片格式'))
    await renderLoaded()

    fireEvent.change(screen.getByLabelText(UPLOAD_INPUT), { target: { files: [makeFile()] } })

    expect(await screen.findByText('无法识别的图片格式')).toBeTruthy()
    expect(screen.getAllByText(EMPTY_HINT).length).toBeGreaterThan(0)
  })

  it('shows 未识别 when the AI semantics are missing', async () => {
    const noSemantics: Clothes = {
      ...shirt,
      category: null,
      sub_category: null,
      color: null,
      style: null,
      season: null,
    }

    vi.mocked(client.fetchWardrobe).mockResolvedValue([noSemantics])

    render(<Wardrobe />)

    expect(await screen.findAllByText('未识别')).toBeTruthy()
  })
})

describe('Wardrobe 删除衣物', () => {
  it('asks before deleting and does nothing when the user cancels', async () => {
    await renderLoaded([shirt])
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)

    fireEvent.click(screen.getByLabelText('删除 上衣 1'))

    expect(confirm).toHaveBeenCalled()
    expect(client.deleteClothes).not.toHaveBeenCalled()
    expect(screen.getByText('T恤')).toBeTruthy()
  })

  it('removes the item after confirmation', async () => {
    // 传错的图（模特挡脸、购物 App 带水印的图）能在 UI 里删掉，不用去翻数据库
    await renderLoaded([shirt])

    fireEvent.click(screen.getByLabelText('删除 上衣 1'))

    await waitFor(() => expect(client.deleteClothes).toHaveBeenCalledWith(1))
    expect(await screen.findByText(EMPTY_HINT)).toBeTruthy()
  })

  it('keeps the item and shows the server message when deletion fails', async () => {
    vi.mocked(client.deleteClothes).mockRejectedValue(new Error('衣物不存在'))
    await renderLoaded([shirt])

    fireEvent.click(screen.getByLabelText('删除 上衣 1'))

    expect(await screen.findByText('衣物不存在')).toBeTruthy()
    expect(screen.getByText('T恤')).toBeTruthy()
  })

  it('ignores a second click while the first delete is still in flight', async () => {
    // 第二次请求会拿到 404「衣物不存在」，用户看到的是一个莫名其妙的报错
    vi.mocked(client.deleteClothes).mockReturnValue(new Promise(() => {}))
    await renderLoaded([shirt])

    fireEvent.click(screen.getByLabelText('删除 上衣 1'))
    fireEvent.click(screen.getByLabelText('删除 上衣 1'))

    expect(client.deleteClothes).toHaveBeenCalledTimes(1)
  })
})
