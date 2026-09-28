import { type ChangeEvent, useCallback, useEffect, useRef, useState } from 'react'
import { deleteClothes, fetchWardrobe, uploadClothes } from '../api/client'
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
  // 删除在飞行中时挡掉第二次点击：第二次请求会拿到 404，用户看到的是一句莫名其妙的报错
  const deletingRef = useRef(false)

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

  async function handleDelete(id: number) {
    if (deletingRef.current) return
    // 删了就找不回来了，图片文件也一起没：先问一句
    if (!window.confirm('删除这件衣物？图片文件也会一起删掉，无法恢复。')) return

    deletingRef.current = true
    setError(null)
    try {
      await deleteClothes(id)
      setItems((prev) => prev.filter((item) => item.id !== id))
    } catch (err) {
      setError(messageOf(err, '删除失败'))
    } finally {
      deletingRef.current = false
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
        <WardrobeGrid items={items} onDelete={handleDelete} />
      )}
    </div>
  )
}
