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

interface Props {
  items: Clothes[]
  /** 选中态。与 onToggle 一起传才启用选择模式 */
  selectedIds?: number[]
  /** 不传 = 只读模式，渲染结果与加选择功能之前完全一致（Home / Wardrobe 依赖这点） */
  onToggle?: (id: number) => void
}

export default function WardrobeGrid({ items, selectedIds, onToggle }: Props) {
  function card(item: Clothes) {
    return (
      <>
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
      </>
    )
  }

  if (!onToggle) {
    return (
      <div className="grid grid-cols-2 gap-3">
        {items.map((item) => (
          <div
            key={item.id}
            className="bg-white rounded-lg shadow-sm border border-gray-100 overflow-hidden"
          >
            {card(item)}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 gap-3">
      {items.map((item) => {
        const selected = selectedIds?.includes(item.id) ?? false
        return (
          /* 整张卡片包在 label 里：点图也能勾选，手机上不用瞄准小方块 */
          <label
            key={item.id}
            className={`relative block bg-white rounded-lg shadow-sm overflow-hidden cursor-pointer border-2 ${
              selected ? 'border-indigo-500' : 'border-transparent'
            }`}
          >
            <input
              type="checkbox"
              /* 可访问名不能带上语义标签：页面测试用 getByText('T恤') 定位，
                 名字里再出现一次就会多匹配而抛错。也不放可见文本节点。 */
              aria-label={`选择 ${item.category ?? '衣物'} ${item.id}`}
              checked={selected}
              onChange={() => onToggle(item.id)}
              className="absolute left-2 top-2 z-10 h-5 w-5 cursor-pointer accent-indigo-600"
            />
            {card(item)}
          </label>
        )
      })}
    </div>
  )
}
