// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import Login from './Login'

vi.mock('../api/client')

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderLogin(configured = true) {
  const onSuccess = vi.fn()
  render(<Login configured={configured} onSuccess={onSuccess} />)
  return { onSuccess }
}

function submit(password: string) {
  fireEvent.change(screen.getByLabelText('访问密码'), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: '登录' }))
}

describe('Login', () => {
  it('submits the password and calls onSuccess', async () => {
    vi.mocked(client.login).mockResolvedValue(undefined)
    const { onSuccess } = renderLogin()

    submit('hunter2')

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1))
    expect(client.login).toHaveBeenCalledWith('hunter2')
  })

  it('shows the server message when the password is wrong', async () => {
    vi.mocked(client.login).mockRejectedValue(new Error('密码错误'))
    const { onSuccess } = renderLogin()

    submit('wrong')

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('密码错误')
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('keeps the button disabled while the request is in flight', async () => {
    let resolveLogin!: () => void
    vi.mocked(client.login).mockReturnValue(
      new Promise<void>((resolve) => {
        resolveLogin = resolve
      }),
    )
    const { onSuccess } = renderLogin()

    submit('hunter2')

    const button = screen.getByRole('button', { name: '登录中…' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)

    resolveLogin()
    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
  })

  it('disables submitting when the password is empty', () => {
    renderLogin()

    const button = screen.getByRole('button', { name: '登录' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
  })

  it('shows setup instructions and blocks the form when no password is configured', () => {
    renderLogin(false)

    expect(screen.getByText(/还没有设置访问密码/)).toBeTruthy()
    const button = screen.getByRole('button', { name: '登录' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
  })
})
