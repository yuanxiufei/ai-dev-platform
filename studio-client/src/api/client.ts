import axios, { type AxiosError } from 'axios'

// ============================================
// API Client — unified HTTP + Toast error handling
// ============================================

// ─── Toast (pure DOM, no framework deps) ──────

let _container: HTMLDivElement | null = null

function getContainer(): HTMLDivElement {
  if (_container) return _container
  _container = document.createElement('div')
  _container.className = 'toast-container'
  _container.innerHTML = ''
  document.body.appendChild(_container)

  // Inject styles once
  const style = document.createElement('style')
  style.textContent = `
.toast-container{position:fixed;top:12px;right:16px;z-index:99999;display:flex;flex-direction:column;gap:8px;pointer-events:none}
.toast-item{pointer-events:auto;padding:10px 16px;border-radius:8px;color:#fff;font-size:13px;line-height:1.4;max-width:380px;box-shadow:0 4px 16px rgba(0,0,0,.25);animation:toast-in .25s ease;backdrop-filter:blur(8px)}
.toast-error{background:rgba(239,68,68,.92)}
.toast-success{background:rgba(34,197,94,.92)}
.toast-info{background:rgba(59,130,246,.92)}
@keyframes toast-in{from{opacity:0;transform:translateX(24px)}to{opacity:1;transform:translateX(0)}}
`
  document.head.appendChild(style)
  return _container
}

function showToast(message: string, type: 'error' | 'success' | 'info' = 'error'): void {
  if (typeof document === 'undefined') return
  const container = getContainer()
  const el = document.createElement('div')
  el.className = `toast-item toast-${type}`
  el.textContent = message
  container.appendChild(el)
  setTimeout(() => el.remove(), 4000)
}

function extractErrorMessage(err: AxiosError): string {
  if (err.response?.data) {
    const data = err.response.data as any
    return data?.detail ?? data?.message ?? data?.error ?? `请求失败 (${err.response.status})`
  }
  if (err.code === 'ECONNABORTED') return '请求超时，请检查网络连接'
  if (err.code === 'ERR_NETWORK') return '无法连接到服务器'
  return err.message || '未知网络错误'
}

// ─── Axios Instance ──────────────────────────

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (res) => res,
  (err: AxiosError) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
      return Promise.reject(err)
    }
    // Skip toast for 404 on GET
    if (!(err.response?.status === 404 && err.config?.method?.toLowerCase() === 'get')) {
      showToast(extractErrorMessage(err), 'error')
    }
    return Promise.reject(err)
  },
)

export { showToast }
export default apiClient
