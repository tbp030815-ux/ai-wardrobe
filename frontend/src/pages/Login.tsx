import { type FormEvent, useState } from 'react'
import { login } from '../api/client'

interface Props {
  /** 后端是否配置了访问密码。false 时表单禁用并展示设置指引 */
  configured: boolean
  onSuccess: () => void
}

function messageOf(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

export default function Login({ configured, onSuccess }: Props) {
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!configured || !password || submitting) return

    setSubmitting(true)
    setError(null)
    try {
      await login(password)
      onSuccess()
    } catch (err) {
      setError(messageOf(err, '登录失败，请稍后重试'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-sm bg-white rounded-lg shadow-sm border border-gray-100 p-6">
        <h1 className="text-xl font-bold text-gray-900">AI 智能衣橱</h1>
        <p className="mt-1 text-sm text-gray-500">输入访问密码后使用</p>

        {!configured && (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            还没有设置访问密码。请在 backend 目录运行
            <code className="mx-1 rounded bg-amber-100 px-1">scripts/set_password.py</code>
            生成密码，然后重启后端。
          </div>
        )}

        <form className="mt-5 space-y-3" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="password" className="block text-sm text-gray-700">
              访问密码
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={!configured || submitting}
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-gray-100"
            />
          </div>

          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={!configured || submitting || !password}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-gray-300"
          >
            {submitting ? '登录中…' : '登录'}
          </button>
        </form>
      </div>
    </div>
  )
}
