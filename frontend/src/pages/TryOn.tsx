import { type ChangeEvent, useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  fetchModels,
  fetchOutfits,
  fetchWardrobe,
  generateTryOn,
  uploadModel,
} from '../api/client'
import WardrobeGrid from '../components/WardrobeGrid'
import type { Clothes, Model, TryOnResult } from '../types'
import { MAX_TRYON_GARMENTS, parseIdsParam } from '../utils/tryonIds'
import { buildVariants } from '../utils/variants'

function messageOf(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

/** 按部位数一数，哪个部位被勾了多件 */
function countByRole(items: Clothes[]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const item of items) {
    const key = item.role ?? ''
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  return counts
}

export default function TryOn() {
  const [items, setItems] = useState<Clothes[]>([])
  const [itemsLoading, setItemsLoading] = useState(true)
  const [models, setModels] = useState<Model[]>([])
  const [modelId, setModelId] = useState<number | null>(null)
  const [uploadingModel, setUploadingModel] = useState(false)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [results, setResults] = useState<TryOnResult[]>([])
  const [generating, setGenerating] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [variantErrors, setVariantErrors] = useState<string[]>([])

  const modelInputRef = useRef<HTMLInputElement>(null)
  const appliedParamRef = useRef(false)
  const cancelledRef = useRef(false)

  const [searchParams] = useSearchParams()

  const load = useCallback(async () => {
    try {
      const [wardrobe, modelList, history] = await Promise.all([
        fetchWardrobe(),
        fetchModels(),
        fetchOutfits(),
      ])
      setItems(wardrobe)
      setModels(modelList)
      // 保留用户已经点过的选择（effect 重跑时不该被重置）
      setModelId((prev) => prev ?? modelList.find((m) => m.is_default)?.id ?? modelList[0]?.id ?? null)
      // 历史里没有 warnings（后端不落库），补空数组让结果卡片只有一种形状
      setResults(history.map((row) => ({ ...row, warnings: [] })))
    } catch (err) {
      setError(messageOf(err, '加载失败'))
    } finally {
      setItemsLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  // 离开页面时中断对比循环：剩下的图没必要再花钱生成
  useEffect(() => () => {
    cancelledRef.current = true
  }, [])

  // 计时器不是付费调用，放 effect 里没问题；生成本身绝不能进 effect
  useEffect(() => {
    if (!generating) return
    const started = Date.now()
    setElapsed(0)
    const timer = setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    )
    return () => clearInterval(timer)
  }, [generating])

  useEffect(() => {
    // 只应用一次，且必须等衣物到齐 —— 抢跑会和拉取赛跑，谁后到谁赢。
    // 用 ref 而不是 state：从 /tryon?ids=1 点导航栏「AI 试穿」不会重挂载组件，
    // 依赖 searchParams 再跑一次会把用户已经改过的勾选清空。
    if (appliedParamRef.current || itemsLoading) return
    appliedParamRef.current = true

    const wanted = parseIdsParam(searchParams.get('ids'))
    if (wanted.length === 0) return
    // 链接会比衣物活得久，与当前的衣柜求交集
    setSelectedIds(items.filter((item) => wanted.includes(item.id)).map((item) => item.id))
  }, [itemsLoading, items, searchParams])

  function toggle(id: number) {
    if (selectedIds.includes(id)) {
      setSelectedIds(selectedIds.filter((selected) => selected !== id))
      return
    }
    if (selectedIds.length >= MAX_TRYON_GARMENTS) {
      setError(`一次最多试穿 ${MAX_TRYON_GARMENTS} 件衣物`)
      return
    }
    setSelectedIds([...selectedIds, id])
  }

  async function handleModelFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = '' // 清空以便再次选择同一个文件
    if (!file) return

    setUploadingModel(true)
    setError(null)
    try {
      const created = await uploadModel(file)
      // 保持「默认排最前，其余最新优先」的顺序，与后端一致
      setModels((prev) => [
        ...prev.filter((m) => m.is_default),
        created,
        ...prev.filter((m) => !m.is_default),
      ])
      setModelId(created.id) // 刚传的马上用上
    } catch (err) {
      setError(messageOf(err, '模特照上传失败'))
    } finally {
      setUploadingModel(false)
    }
  }

  /** 一次点击 = 一次调用 = 一张图。**只能从事件回调里调**：main.tsx 开了 StrictMode，
   *  effect 在 dev 下双跑，放进 effect 就是一次点击打两次付费 API。 */
  async function generate(ids: number[]) {
    return generateTryOn(ids, modelId ?? undefined)
  }

  async function handleGenerate() {
    setGenerating(true)
    setError(null)
    setVariantErrors([])
    try {
      const result = await generate(selectedIds)
      setResults((prev) => [result, ...prev])
    } catch (err) {
      setError(messageOf(err, '生成失败'))
    } finally {
      setGenerating(false)
    }
  }

  async function handleCompare() {
    setGenerating(true)
    setError(null)
    setVariantErrors([])

    const failures: string[] = []
    try {
      // 串行而不是并行：逐张上屏、避开限流、用户能中途放弃。并行只会换来一个 429
      for (const [index, ids] of variants.entries()) {
        if (cancelledRef.current) break
        try {
          const result = await generate(ids)
          if (cancelledRef.current) break
          setResults((prev) => [result, ...prev])
        } catch (err) {
          // 单张失败只标这一张，绝不能丢掉已经成功的结果
          failures.push(`第 ${index + 1} 组失败：${messageOf(err, '生成失败')}`)
          setVariantErrors([...failures])
        }
      }
    } finally {
      setGenerating(false)
    }
  }

  function reselect(ids: number[]) {
    setSelectedIds(ids.filter((id) => items.some((item) => item.id === id)))
  }

  const selectedItems = selectedIds
    .map((id) => items.find((item) => item.id === id))
    .filter((item): item is Clothes => Boolean(item))
  const variants = buildVariants(selectedItems)
  const hasTie = [...countByRole(selectedItems).values()].some((count) => count > 1)
  const blocked = generating || selectedIds.length === 0 || modelId === null

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">AI 试穿</h2>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* 模特 */}
      <section className="bg-white rounded-lg p-4 shadow-sm border border-gray-100 mb-4">
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-sm font-medium text-gray-700">模特</h3>
          <button
            type="button"
            onClick={() => modelInputRef.current?.click()}
            disabled={uploadingModel}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {uploadingModel ? '上传中…' : '+ 添加模特照'}
          </button>
          <input
            ref={modelInputRef}
            type="file"
            accept="image/*"
            aria-label="选择模特全身照"
            className="hidden"
            onChange={handleModelFile}
          />
        </div>

        {models.length === 0 ? (
          <p className="text-sm text-gray-500">
            上传一张全身照，试穿时的身高、体型和姿势都以它为准
          </p>
        ) : (
          <div className="flex gap-3 overflow-x-auto">
            {models.map((item) => (
              <button
                key={item.id}
                type="button"
                aria-label={`模特 ${item.id}`}
                aria-pressed={item.id === modelId}
                onClick={() => setModelId(item.id)}
                className={`relative shrink-0 overflow-hidden rounded-lg border-2 ${
                  item.id === modelId ? 'border-indigo-500' : 'border-transparent'
                }`}
              >
                <img src={item.image_path} alt="" className="h-28 w-auto object-cover" />
                {item.is_default && (
                  <span className="absolute inset-x-0 bottom-0 bg-black/50 text-center text-[10px] text-white">
                    默认
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </section>

      {/* 衣物 */}
      <section className="mb-4">
        <h3 className="text-sm font-medium text-gray-700 mb-2">
          选择衣物{selectedIds.length > 0 && `（已选 ${selectedIds.length} 件）`}
        </h3>
        {itemsLoading ? (
          <div className="bg-white rounded-lg p-6 shadow-sm border border-gray-100 text-center text-gray-500">
            加载中…
          </div>
        ) : items.length === 0 ? (
          <div className="bg-white rounded-lg p-6 shadow-sm border border-gray-100 text-center text-gray-500">
            衣柜还是空的，先去添加衣物
          </div>
        ) : (
          <WardrobeGrid items={items} selectedIds={selectedIds} onToggle={toggle} />
        )}
      </section>

      {/* 操作 */}
      <div className="mb-4 space-y-2">
        {hasTie && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">
            同一个部位勾了多件，生成时只会用其中一件；想逐个看效果请用「对比生成」
          </div>
        )}

        {/* 触发条件是「参考衣物与手臂区域重叠」而非「换上衣」：手臂搭在胯上挡住裤子时，只换裤子一样会漂 */}
        <p className="text-xs text-gray-500">
          手臂姿势可能与原图有差异：参考衣物与手臂区域重叠时，模型要重绘被挡住的部位，可能顺手改动手臂位置。
        </p>

        {modelId === null && (
          <p className="text-sm text-amber-700">请先上传一张模特全身照</p>
        )}

        <button
          type="button"
          onClick={handleGenerate}
          disabled={blocked}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          生成试穿
        </button>

        {variants.length > 0 && (
          <button
            type="button"
            onClick={handleCompare}
            disabled={blocked}
            className="w-full rounded-lg bg-white px-4 py-2 text-sm font-medium text-indigo-700 border border-indigo-300 hover:bg-indigo-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            对比生成（{variants.length} 张）
          </button>
        )}

        {generating && (
          <p className="flex items-center gap-2 text-sm text-indigo-700">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-300 border-t-indigo-600" />
            已等待 {elapsed} 秒…（一张通常要 30-60 秒）
          </p>
        )}

        {variantErrors.map((message) => (
          <div
            key={message}
            className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700"
          >
            {message}
          </div>
        ))}
      </div>

      {/* 结果 + 历史 */}
      {results.length > 0 && (
        <section className="space-y-4">
          <h3 className="text-sm font-medium text-gray-700">试穿结果</h3>
          {results.map((result) => (
            <div
              key={result.id}
              className="bg-white rounded-lg shadow-sm border border-gray-100 overflow-hidden"
            >
              {/* 宽高比跟随模特照，不强制切方 */}
              <img
                src={result.result_image_url}
                alt={`试穿结果 ${result.id}`}
                className="w-full h-auto"
              />
              <div className="p-3 space-y-2">
                <div className="flex justify-between items-center text-xs text-gray-500">
                  <span>{result.created_at}</span>
                  <button
                    type="button"
                    onClick={() => reselect(result.clothes_ids)}
                    className="text-indigo-600 hover:text-indigo-800"
                  >
                    改用这几件
                  </button>
                </div>
                {result.warnings.map((warning) => (
                  <p key={warning} className="text-xs text-amber-700">
                    {warning}
                  </p>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  )
}
