// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as client from './api/client'
import App from './App'
import { navigateTo } from './utils/nextUrl'

vi.mock('./api/client')
// 只替换整页导航（jsdom 里 location.replace 不可 spy），safeNextPath 保持真实实现
vi.mock('./utils/nextUrl', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./utils/nextUrl')>()
  return { ...actual, navigateTo: vi.fn() }
})
// 门禁测试只关心「显示登录页还是应用」，页面内容整块替掉，避免它们各自的请求干扰
vi.mock('./pages/Home', () => ({ default: () => <div>今日推荐页面</div> }))
vi.mock('./pages/Wardrobe', () => ({ default: () => <div>衣柜页面</div> }))
vi.mock('./pages/TryOn', () => ({ default: () => <div>试穿页面</div> }))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  window.history.replaceState({}, '', '/')
})

function signedOut(configured = true) {
  vi.mocked(client.fetchAuthStatus).mockResolvedValue({ authenticated: false, configured })
}

describe('App 登录门禁', () => {
  it('shows a checking state before the auth status resolves', () => {
    vi.mocked(client.fetchAuthStatus).mockReturnValue(new Promise(() => {}))

    render(<App />)

    expect(screen.getByText('正在检查登录状态…')).toBeTruthy()
  })

  it('shows the login page when the session is missing', async () => {
    signedOut()

    render(<App />)

    expect(await screen.findByLabelText('访问密码')).toBeTruthy()
    expect(screen.queryByText('今日推荐页面')).toBeNull()
  })

  it('shows setup instructions when no password is configured', async () => {
    signedOut(false)

    render(<App />)

    expect(await screen.findByText(/还没有设置访问密码/)).toBeTruthy()
  })

  it('shows the app when already authenticated', async () => {
    vi.mocked(client.fetchAuthStatus).mockResolvedValue({ authenticated: true, configured: true })

    render(<App />)

    expect(await screen.findByText('今日推荐页面')).toBeTruthy()
    expect(screen.getByRole('link', { name: '我的衣柜' })).toBeTruthy()
  })

  it('enters the app after a successful login', async () => {
    signedOut()
    vi.mocked(client.login).mockResolvedValue(undefined)

    render(<App />)

    fireEvent.change(await screen.findByLabelText('访问密码'), {
      target: { value: 'hunter2' },
    })
    fireEvent.click(screen.getByRole('button', { name: '登录' }))

    expect(await screen.findByText('今日推荐页面')).toBeTruthy()
  })

  it('returns to the requested image after login', async () => {
    signedOut()
    vi.mocked(client.login).mockResolvedValue(undefined)
    window.history.replaceState({}, '', '/?next=%2Fuploads%2Fg1.jpg')

    render(<App />)

    fireEvent.change(await screen.findByLabelText('访问密码'), {
      target: { value: 'hunter2' },
    })
    fireEvent.click(screen.getByRole('button', { name: '登录' }))

    await waitFor(() =>
      expect(vi.mocked(navigateTo)).toHaveBeenCalledWith('/uploads/g1.jpg'),
    )
  })

  it('does not follow an off-site next target after login', async () => {
    signedOut()
    vi.mocked(client.login).mockResolvedValue(undefined)
    window.history.replaceState({}, '', '/?next=https%3A%2F%2Fevil.com%2Fsteal')

    render(<App />)

    fireEvent.change(await screen.findByLabelText('访问密码'), {
      target: { value: 'hunter2' },
    })
    fireEvent.click(screen.getByRole('button', { name: '登录' }))

    expect(await screen.findByText('今日推荐页面')).toBeTruthy()
    expect(vi.mocked(navigateTo)).not.toHaveBeenCalled()
  })

  it('returns to the login page after logging out', async () => {
    vi.mocked(client.fetchAuthStatus).mockResolvedValue({ authenticated: true, configured: true })
    vi.mocked(client.logout).mockResolvedValue(undefined)

    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '退出' }))

    expect(await screen.findByLabelText('访问密码')).toBeTruthy()
    expect(client.logout).toHaveBeenCalledTimes(1)
  })
})
