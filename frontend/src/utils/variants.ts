import type { Clothes } from '../types'

/**
 * 组合爆炸的上限：多个角色同时有多件时，超过这个数就只变一个角色。
 *
 * **不是用户选择的上限** —— 只勾了一个角色的 5 件，就出 5 张，
 * 按钮上写着张数，静默砍掉一张等于吞掉用户的选择。
 */
export const MAX_VARIANTS = 4

/** 识别失败的衣物 role 为 null，它们归入同一个分组 */
const UNKNOWN_ROLE = '__unknown__'

function groupByRole(items: Clothes[]): Map<string, Clothes[]> {
  const groups = new Map<string, Clothes[]>()
  for (const item of items) {
    const key = item.role ?? UNKNOWN_ROLE
    const group = groups.get(key)
    if (group) group.push(item)
    else groups.set(key, [item])
  }
  return groups
}

/**
 * 把勾选的衣物拆成「对比生成」的变体列表，每个变体是一组 clothes_ids。
 *
 * 核心约束：**每个变体里每个角色只能出现一件**。同角色两件会让后端按
 * 「同部位以先列出的为准」的规则丢掉一件，用户看到的和勾选的就不是一回事了。
 *
 * 没有可变的角色（每个角色都只有一件）时返回空数组 —— 那种情况下「对比生成」
 * 和「生成试穿」完全等价，不该多出一个按钮。
 */
export function buildVariants(items: Clothes[], max = MAX_VARIANTS): number[][] {
  const groups = [...groupByRole(items).values()]
  const varying = groups.filter((group) => group.length > 1)
  if (varying.length === 0) return []

  const product = varying.reduce((count, group) => count * group.length, 1)
  // 笛卡尔积超限时只变单品最多的那个角色：3 件上衣 × 2 条裤子 = 6 张，
  // 用户要等 6 分钟、付 6 次钱，而他大概率只想比上衣
  const axes = new Set(
    product <= max ? varying : [varying.reduce((a, b) => (b.length > a.length ? b : a))],
  )

  let variants: number[][] = [[]]
  for (const group of groups) {
    if (axes.has(group)) {
      // 要变的角色：把当前每个变体展开成「这个角色的每一件」各一份
      const expanded: number[][] = []
      for (const variant of variants) {
        for (const item of group) expanded.push([...variant, item.id])
      }
      variants = expanded
    } else {
      // 不参与变化的角色：一律取第一件，保持不变才能看出差异
      for (const variant of variants) variant.push(group[0].id)
    }
  }
  return variants
}
