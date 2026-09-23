import type { Clothes } from '../types'

/** AI 识别出的语义标签，全为空说明识别未完成 */
function Semantics({ item }: { item: Clothes }) {
  const labels = [item.category, item.sub_category, item.color, item.style, item.season].filter(
    (label): label is string => Boolean(label),
  )

  if (labels.length === 0) {
    return <span className="text-xs text-gray-400">未识别</span>
  }

  return (
    <div className="flex flex-wrap gap-1">
      {labels.map((label) => (
        <span key={label} className="text-xs bg-indigo-50 text-indigo-700 px-1.5 py-0.5 rounded">
          {label}
        </span>
      ))}
    </div>
  )
}

export default function WardrobeGrid({ items }: { items: Clothes[] }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      {items.map((item) => (
        <div
          key={item.id}
          className="bg-white rounded-lg shadow-sm border border-gray-100 overflow-hidden"
        >
          {/* 浅灰底衬托抠图后的透明底 PNG */}
          <div className="bg-gray-100 aspect-square flex items-center justify-center">
            <img
              src={item.cropped_path ?? item.image_path}
              alt={item.category ?? '衣物'}
              className="w-full h-full object-contain"
            />
          </div>
          <div className="p-2">
            <Semantics item={item} />
          </div>
        </div>
      ))}
    </div>
  )
}
