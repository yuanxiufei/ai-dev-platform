/**
 * 设备检测 — 在路由级别判断当前是否为移动端。
 * 注意：这是同步检测（首次路由匹配时执行），不会响应窗口 resize。
 * 如需响应式调整，页面内仍可使用 useIsMobile()。
 */
export function isMobileDevice(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(max-width: 767px)').matches
}
