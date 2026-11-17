import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { fetchAuthStatus, logout, setUnauthorizedHandler } from './api/client'
import Home from './pages/Home'
import Login from './pages/Login'
import TryOn from './pages/TryOn'
import Wardrobe from './pages/Wardrobe'
import { navigateTo, safeNextPath } from './utils/nextUrl'

type AuthState =
  | { status: 'checking' }
  | { status: 'anonymous'; configured: boolean }
  | { status: 'authenticated' }

function App() {
  const [auth, setAuth] = useState<AuthState>({ status: 'checking' })

  useEffect(() => {
    // 会话过期或密码被改后，任何业务请求都会 401 —— client 统一通知，这里退回登录页
    setUnauthorizedHandler(() => setAuth({ status: 'anonymous', configured: true }))

    let cancelled = false
    void fetchAuthStatus()
      .then((me) => {
        if (cancelled) return
        setAuth(
          me.authenticated
            ? { status: 'authenticated' }
            : { status: 'anonymous', configured: me.configured },
        )
      })
      .catch(() => {
        // 后端连不上也落到登录页：否则用户只能看到一块永远转圈的空白
        if (!cancelled) setAuth({ status: 'anonymous', configured: true })
      })

    return () => {
      cancelled = true
      setUnauthorizedHandler(null)
    }
  }, [])

  function handleLoginSuccess() {
    setAuth({ status: 'authenticated' })
    // 从图片 URL 被踢到登录页的，登录后回到那张图；普通登录没有 next，留在应用里
    const next = safeNextPath(window.location.search, window.location.origin)
    if (next) navigateTo(next)
  }

  async function handleLogout() {
    try {
      await logout()
    } catch {
      // 退出请求失败也回登录页：后端都不可用了，留着应用也没有意义
    }
    setAuth({ status: 'anonymous', configured: true })
  }

  if (auth.status === 'checking') {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center text-sm text-gray-500">
        正在检查登录状态…
      </div>
    )
  }

  if (auth.status === 'anonymous') {
    return (
      <Login
        configured={auth.configured}
        onSuccess={handleLoginSuccess}
      />
    )
  }

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        <nav className="bg-white shadow-sm border-b border-gray-200">
          <div className="max-w-lg mx-auto px-4 py-3 flex justify-between items-center">
            <h1 className="text-lg font-bold text-gray-900">AI 智能衣橱</h1>
            <div className="flex items-center gap-4">
              <NavLink to="/" className="text-gray-600 hover:text-gray-900">今日推荐</NavLink>
              <NavLink to="/wardrobe" className="text-gray-600 hover:text-gray-900">我的衣柜</NavLink>
              <NavLink to="/tryon" className="text-gray-600 hover:text-gray-900">AI 试穿</NavLink>
              <button
                type="button"
                onClick={handleLogout}
                className="text-gray-500 hover:text-gray-900"
              >
                退出
              </button>
            </div>
          </div>
        </nav>
        <main className="max-w-lg mx-auto px-4 py-6">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/wardrobe" element={<Wardrobe />} />
            <Route path="/tryon" element={<TryOn />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
