// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Recommendation, RecommendedItem } from '../types'
import * as client from '../api/client'
import Home from './Home'

vi.mock('../api/client')

const tee: RecommendedItem = {
  id: 1,
  user_id: 1,
  image_path: '/uploads/a.jpg',
  cropped_path: '/uploads/a_cropped.png',
  category: '上衣',
  sub_category: 'T恤',
  color: '蓝色',
  style: '休闲',
  season: '夏季',
  tags: null,
  created_at: '2026-09-24 10:00:00',
  role: '上衣',
}

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
  occasion: '休闲',
  source: 'llm',
  reason: '清爽舒适，适合今天的天气',
  items: [tee],
  gaps: [],
}

const CITY_INPUT = '城市'
const LOADING_HINT = '正在根据天气挑选…'

async function renderLoaded(rec: Recommendation = sampleRecommendation) {
  vi.mocked(client.fetchRecommendation).mockResolvedValue(rec)
  render(<Home />)
  await screen.findByText(rec.weather.description)
}

beforeEach(() => {
  // jsdom 30 不再提供 localStorage，用内存版 stub（Home 组件内已有 try/catch 兜底）
  const store = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    clear: () => store.clear(),
  })
  vi.mocked(client.fetchRecommendation).mockResolvedValue(sampleRecommendation)
})

afterEach(() => {
  cleanup() // vitest 未开 globals，testing-library 不会自动清理 DOM
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('Home', () => {
  it('renders the weather card with city, description and temperature', async () => {
    await renderLoaded()

    expect(screen.getByText('上海')).toBeTruthy()
    expect(screen.getByText('晴间多云')).toBeTruthy()
    expect(screen.getByText('29°C')).toBeTruthy() // Math.round(28.8)
  })

  it('renders the recommended items', async () => {
    await renderLoaded()

    expect(await screen.findByAltText('上衣')).toBeTruthy()
    expect(screen.getByText('T恤')).toBeTruthy()
  })

  it('shows the reason with an AI badge when source is llm', async () => {
    await renderLoaded()

    expect(screen.getByText('AI 精选')).toBeTruthy()
    expect(screen.getByText('清爽舒适，适合今天的天气')).toBeTruthy()
  })

  it('shows a rule badge when the recommendation fell back to rules', async () => {
    await renderLoaded({ ...sampleRecommendation, source: 'rule' })

    expect(screen.getByText('规则推荐')).toBeTruthy()
  })

  it('shows gap hints when the wardrobe is incomplete', async () => {
    await renderLoaded({
      ...sampleRecommendation,
      items: [],
      gaps: ['衣柜里还没有鞋'],
    })

    expect(screen.getByText('衣柜里还没有鞋')).toBeTruthy()
  })

  it('uses the saved city from localStorage on first load', async () => {
    localStorage.setItem('wardrobe:city', '杭州')

    render(<Home />)
    await screen.findByText('晴间多云')

    expect(client.fetchRecommendation).toHaveBeenCalledWith('杭州', '休闲')
  })

  it('submits a new city, re-requests and remembers it', async () => {
    await renderLoaded()

    fireEvent.change(screen.getByLabelText(CITY_INPUT), { target: { value: ' 杭州 ' } })
    fireEvent.click(screen.getByRole('button', { name: '更新' }))

    expect(client.fetchRecommendation).toHaveBeenCalledWith('杭州', '休闲')
    expect(localStorage.getItem('wardrobe:city')).toBe('杭州')
  })

  it('re-requests when the occasion changes', async () => {
    await renderLoaded()

    fireEvent.click(screen.getByRole('button', { name: '运动' }))

    expect(client.fetchRecommendation).toHaveBeenCalledWith('上海', '运动')
  })

  it('shows the server message when the request fails and keeps the input', async () => {
    vi.mocked(client.fetchRecommendation).mockRejectedValue(
      new Error('天气服务暂时不可用，请稍后重试'),
    )

    render(<Home />)

    expect(await screen.findByText('天气服务暂时不可用，请稍后重试')).toBeTruthy()
    expect(screen.getByLabelText(CITY_INPUT)).toBeTruthy()
  })

  it('shows a loading hint while fetching', () => {
    vi.mocked(client.fetchRecommendation).mockReturnValue(new Promise(() => {}))

    render(<Home />)

    expect(screen.getByText(LOADING_HINT)).toBeTruthy()
  })
})
