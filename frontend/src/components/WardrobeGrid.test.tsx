// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Clothes } from '../types'
import WardrobeGrid from './WardrobeGrid'

afterEach(cleanup)

const shirt: Clothes = {
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
  created_at: '2026-09-25 10:00:00',
  role: '上衣',
}

const shoes: Clothes = {
  ...shirt,
  id: 2,
  category: '鞋',
  sub_category: '运动鞋',
  role: '鞋',
}

describe('WardrobeGrid 只读模式（不传 onToggle）', () => {
  it('renders no selection control at all', () => {
    render(<WardrobeGrid items={[shirt]} />)

    expect(screen.queryByRole('checkbox')).toBeNull()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('still renders the item image and tags', () => {
    render(<WardrobeGrid items={[shirt]} />)

    expect(screen.getByAltText('上衣')).toBeTruthy()
    expect(screen.getByText('T恤')).toBeTruthy()
  })
})

describe('WardrobeGrid 选择模式（传了 onToggle）', () => {
  it('renders one toggle per item', () => {
    render(<WardrobeGrid items={[shirt, shoes]} onToggle={() => {}} selectedIds={[]} />)

    expect(screen.getAllByRole('checkbox')).toHaveLength(2)
  })

  it('reports the clicked item id', () => {
    const onToggle = vi.fn()
    render(<WardrobeGrid items={[shirt, shoes]} onToggle={onToggle} selectedIds={[]} />)

    fireEvent.click(screen.getByLabelText('选择 鞋 2'))

    expect(onToggle).toHaveBeenCalledWith(2)
  })

  it('marks only the selected items as checked', () => {
    render(<WardrobeGrid items={[shirt, shoes]} onToggle={() => {}} selectedIds={[2]} />)

    expect(screen.getByLabelText('选择 鞋 2')).toHaveProperty('checked', true)
    expect(screen.getByLabelText('选择 上衣 1')).toHaveProperty('checked', false)
  })

  it('keeps the accessible name out of the semantic labels', () => {
    // 选择控件的可访问名若含「T恤」，页面测试里的 getByText('T恤') 就会多匹配而抛错
    render(<WardrobeGrid items={[shirt]} onToggle={() => {}} selectedIds={[]} />)

    expect(screen.getByText('T恤')).toBeTruthy()
  })

  it('names the toggle with a fallback when the item was never recognized', () => {
    const unknown: Clothes = { ...shirt, id: 9, category: null, sub_category: null, role: null }
    render(<WardrobeGrid items={[unknown]} onToggle={() => {}} selectedIds={[]} />)

    expect(screen.getByLabelText('选择 衣物 9')).toBeTruthy()
  })

  it('still renders the item image and tags', () => {
    render(<WardrobeGrid items={[shirt]} onToggle={() => {}} selectedIds={[]} />)

    expect(screen.getByAltText('上衣')).toBeTruthy()
    expect(screen.getByText('T恤')).toBeTruthy()
  })

  it('never renders delete controls — a button inside the label would toggle selection', () => {
    // 整张卡片是 <label>，嵌套的 button 点下去会连带勾选/取消勾选。删除只在衣柜页提供
    render(
      <WardrobeGrid items={[shirt]} onToggle={() => {}} selectedIds={[]} onDelete={() => {}} />,
    )

    expect(screen.queryByLabelText('删除 上衣 1')).toBeNull()
  })
})

describe('WardrobeGrid 只读模式 + onDelete', () => {
  it('renders one delete control per item', () => {
    render(<WardrobeGrid items={[shirt, shoes]} onDelete={() => {}} />)

    expect(screen.getByLabelText('删除 上衣 1')).toBeTruthy()
    expect(screen.getByLabelText('删除 鞋 2')).toBeTruthy()
  })

  it('reports the id of the item to delete', () => {
    const onDelete = vi.fn()
    render(<WardrobeGrid items={[shirt, shoes]} onDelete={onDelete} />)

    fireEvent.click(screen.getByLabelText('删除 鞋 2'))

    expect(onDelete).toHaveBeenCalledWith(2)
  })

  it('keeps the accessible name out of the semantic labels', () => {
    // 与选择控件同理：名字里带「T恤」会让页面测试的 getByText('T恤') 多匹配而抛错
    render(<WardrobeGrid items={[shirt]} onDelete={() => {}} />)

    expect(screen.getByText('T恤')).toBeTruthy()
  })

  it('names the control with a fallback when the item was never recognized', () => {
    const unknown: Clothes = { ...shirt, id: 9, category: null, sub_category: null, role: null }
    render(<WardrobeGrid items={[unknown]} onDelete={() => {}} />)

    expect(screen.getByLabelText('删除 衣物 9')).toBeTruthy()
  })
})
