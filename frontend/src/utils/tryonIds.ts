/**
 * 首页「试穿这套」→ 试穿页的预选参数。
 *
 * 用 query param 而不是 router state：刷新后仍然有效，也能直接分享链接。
 * 代价是入参完全不可信 —— 链接会比它引用的衣物活得久，用户也会手改地址栏。
 */

/** 后端 api/tryon.py 的 MAX_GARMENTS，超了会 400。前端先拦一道，别让用户白等一轮 */
export const MAX_TRYON_GARMENTS = 8

/**
 * 解析 `?ids=3,4`。**静默丢弃**一切不合法的片段，不抛错：
 * 一个被改坏的链接不该让整页白屏。去重且保持原顺序。
 */
export function parseIdsParam(raw: string | null): number[] {
  if (!raw) return []

  const ids: number[] = []
  for (const part of raw.split(',')) {
    const id = Number(part.trim())
    if (Number.isInteger(id) && id > 0 && !ids.includes(id)) ids.push(id)
  }
  return ids
}
