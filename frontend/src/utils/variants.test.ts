import { describe, expect, it } from 'vitest'
import type { Clothes } from '../types'
import { buildVariants } from './variants'

function item(id: number, role: string | null): Clothes {
  return {
    id,
    user_id: 1,
    image_path: `/uploads/${id}.jpg`,
    cropped_path: null,
    category: role,
    sub_category: null,
    color: null,
    style: null,
    season: null,
    tags: null,
    created_at: '2026-09-25 10:00:00',
    role,
  }
}

const topA = item(1, '上衣')
const topB = item(2, '上衣')
const topC = item(3, '上衣')
const pantsA = item(4, '下装')
const pantsB = item(5, '下装')
const shoes = item(6, '鞋')

describe('buildVariants', () => {
  it('returns nothing when nothing is selected', () => {
    expect(buildVariants([])).toEqual([])
  })

  it('returns nothing when every role has exactly one item', () => {
    // 只有一套组合时「对比生成」就是「生成试穿」，不该出两个按钮
    expect(buildVariants([topA, pantsA, shoes])).toEqual([])
  })

  it('returns one variant per item when a single role has several', () => {
    expect(buildVariants([topA, topB, pantsA])).toEqual([
      [1, 4],
      [2, 4],
    ])
  })

  it('returns the cartesian product when two roles have several', () => {
    expect(buildVariants([topA, topB, pantsA, pantsB])).toEqual([
      [1, 4],
      [1, 5],
      [2, 4],
      [2, 5],
    ])
  })

  it('gives every variant exactly one item per role', () => {
    // 同角色两件会让后端按 id 平局规则取一件，用户看到的和选的不一致
    for (const variant of buildVariants([topA, topB, pantsA, pantsB])) {
      expect(variant).toHaveLength(2)
    }
  })

  it('caps the count by varying only the role with the most items', () => {
    // 3×2 = 6 张要等 6 分钟、扣 6 次费；只变上衣出 3 张
    const variants = buildVariants([topA, topB, topC, pantsA, pantsB])

    expect(variants).toEqual([
      [1, 4],
      [2, 4],
      [3, 4],
    ])
  })

  it('breaks a size tie by the order the roles first appear', () => {
    const variants = buildVariants([topA, topB, topC, pantsA, pantsB, item(7, '下装')])

    expect(variants).toEqual([
      [1, 4],
      [2, 4],
      [3, 4],
    ])
  })

  it('does not cap a single role the user explicitly picked', () => {
    // 用户勾了 5 件上衣，按钮就写「对比生成（5 张）」，少出一张等于偷偷吞掉他的选择。
    // MAX_VARIANTS 管的是组合爆炸（3 件上衣 × 2 条裤子 = 6），不是用户的显式选择。
    const many = [1, 2, 3, 4, 5].map((id) => item(id, '上衣'))

    expect(buildVariants(many)).toHaveLength(5)
  })

  it('lets the caller raise the cap', () => {
    const many = [1, 2, 3, 4, 5].map((id) => item(id, '上衣'))

    expect(buildVariants(many, 8)).toHaveLength(5)
  })

  it('keeps the untouched roles on their first item', () => {
    const variants = buildVariants([topA, topB, pantsA, pantsB, shoes])

    for (const variant of variants) expect(variant).toContain(6)
  })

  it('groups items whose role was never recognized together', () => {
    const variants = buildVariants([item(1, null), item(2, null), item(3, '上衣')])

    expect(variants).toEqual([
      [1, 3],
      [2, 3],
    ])
  })
})
