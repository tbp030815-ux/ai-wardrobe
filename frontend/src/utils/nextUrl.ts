/**
 * 从登录页 URL 的 `?next=` 里取安全的目标路径。
 *
 * 登录地址是用户可手工构造的：不校验就是开放重定向 ——
 * `?next=https://evil.com` 会让登录成功后跳到钓鱼站。
 * 只接受解析后与当前页面同源的地址。
 */
export function safeNextPath(search: string, origin: string): string | null {
  const raw = new URLSearchParams(search).get('next')
  if (!raw) return null

  let url: URL
  try {
    url = new URL(raw, origin)
  } catch {
    return null
  }

  if (url.origin !== origin) return null
  return `${url.pathname}${url.search}${url.hash}`
}

/**
 * 整页导航回原地址。图片不是 SPA 路由，必须交给浏览器整页跳转。
 *
 * 单独成函数是为了测试可替换：jsdom 里的 `location.replace` 不可 spy。
 */
export function navigateTo(path: string): void {
  window.location.replace(path)
}
