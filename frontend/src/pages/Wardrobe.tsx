import { type ChangeEvent, useCallback, useEffect, useRef, useState } from 'react'
import { fetchWardrobe, uploadClothes } from '../api/client'
import WardrobeGrid from '../components/WardrobeGrid'
import type { Clothes } from '../types'

function messageOf(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

export default function Wardrobe() {
  const [items, setItems] = useState<Clothes[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      setItems(await fetchWardrobe())
      setError(null)
    } catch (err) {
      setError(messageOf(err, '加载衣柜失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = '' // 清空以便再次选择同一个文件
    if (!file) return

    setUploading(true)
    setError(null)
    try {
      const created = await uploadClothes(file)
      setItems((prev) => [created, ...prev])
    } catch (err) {
      setError(messageOf(err, '上传失败'))
    } finally {
      setUploading(false)
    }
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">我的衣柜</h2>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {uploading ? '上传中…' : '+ 添加衣物'}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          aria-label="选择衣物照片"
          className="hidden"
          onChange={handleFileChange}
        />
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* 抠图 + AI 识别需要十几秒到一分钟，给出明确反馈 */}
      {uploading && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm text-indigo-700">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-300 border-t-indigo-600" />
          AI 正在抠图识别…
        </div>
      )}

      {loading ? (
        <div className="bg-white rounded-lg p-6 shadow-sm border border-gray-100 text-center text-gray-500">
          加载中…
        </div>
      ) : items.length === 0 ? (
        <div className="bg-white rounded-lg p-6 shadow-sm border border-gray-100 text-center text-gray-500">
          暂无衣物，点击右上角添加
        </div>
      ) : (
        <WardrobeGrid items={items} />
      )}
    </div>
  )
}
