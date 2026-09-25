import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { fetchRecommendation } from '../api/client'
import WardrobeGrid from '../components/WardrobeGrid'
import type { Recommendation } from '../types'

const CITY_STORAGE_KEY = 'wardrobe:city'
const DEFAULT_CITY = '上海'
const OCCASIONS = ['通勤', '休闲', '运动', '约会', '正式']
const LOADING_HINT = '正在根据天气挑选…'

/** 读上次输入的城市；隐私模式下 localStorage 可能抛异常，需兜底 */
function readSavedCity(): string {
  try {
    return localStorage.getItem(CITY_STORAGE_KEY) || DEFAULT_CITY
  } catch {
    return DEFAULT_CITY
  }
}

export default function Home() {
  const [city, setCity] = useState(readSavedCity) // 传函数 = 惰性初始化，只读一次
  const [cityInput, setCityInput] = useState(readSavedCity)
  const [occasion, setOccasion] = useState('休闲')
  const [reloadKey, setReloadKey] = useState(0) // 城市没变时也能手动重试
  const [data, setData] = useState<Recommendation | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await fetchRecommendation(city, occasion)
      setData(result)
      setError(null)
    } catch (err) {
      setData(null) // 失败时清空，避免误认旧结果是新城市的
      setError(err instanceof Error ? err.message : '获取推荐失败')
    } finally {
      setLoading(false)
    }
  }, [city, occasion])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const next = cityInput.trim()
    if (!next) return
    setCity(next)
    try {
      localStorage.setItem(CITY_STORAGE_KEY, next)
    } catch {
      // 忽略存储失败
    }
    setReloadKey((k) => k + 1) // 同城重试；换城时 state 变化本身也会触发
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">今日穿搭推荐</h2>

      {/* 城市输入行 */}
      <form onSubmit={handleSubmit} className="flex gap-2 mb-3">
        <input
          aria-label="城市"
          value={cityInput}
          onChange={(e) => setCityInput(e.target.value)}
          placeholder={DEFAULT_CITY}
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <button
          type="submit"
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-500"
        >
          更新
        </button>
      </form>

      {/* 场合按钮组 */}
      <div className="flex gap-2 mb-4">
        {OCCASIONS.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setOccasion(item)}
            className={`rounded-full px-3 py-1 text-sm ${
              occasion === item
                ? 'bg-indigo-600 text-white'
                : 'bg-white text-gray-600 border border-gray-200'
            }`}
          >
            {item}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="bg-white rounded-lg p-6 shadow-sm border border-gray-100 text-center text-gray-500">
          {LOADING_HINT}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : (
        data && (
          <>
            {/* 天气卡片 */}
            <div className="bg-white rounded-lg p-4 shadow-sm border border-gray-100 mb-4">
              <div className="flex justify-between text-sm text-gray-500">
                <span>{data.weather.city}</span>
                <span>{data.weather.description}</span>
              </div>
              <div className="text-3xl font-semibold mt-1">
                {Math.round(data.weather.temperature)}°C
                <span className="text-sm text-gray-400 ml-2">
                  体感 {data.weather.reference_temperature}°C ·{' '}
                  {Math.round(data.weather.temp_min)}~{Math.round(data.weather.temp_max)}°C ·
                  降水 {data.weather.precipitation_probability}%
                </span>
              </div>
            </div>

            {/* 理由 + 来源徽标 */}
            <div className="bg-white rounded-lg p-4 shadow-sm border border-gray-100 mb-4">
              <span className="text-xs bg-indigo-50 text-indigo-700 px-1.5 py-0.5 rounded">
                {data.source === 'llm' ? 'AI 精选' : '规则推荐'}
              </span>
              <p className="mt-2 text-sm text-gray-700">{data.reason}</p>
            </div>

            {/* 缺失提示 */}
            {data.gaps.map((gap) => (
              <div
                key={gap}
                className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
              >
                {gap}
              </div>
            ))}

            {/* 单品：直接复用衣柜网格（RecommendedItem 是 Clothes 的子类型） */}
            {data.items.length > 0 && <WardrobeGrid items={data.items} />}
          </>
        )
      )}
    </div>
  )
}
