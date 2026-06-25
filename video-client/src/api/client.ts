import axios, { type AxiosError } from 'axios'

// ============================================
// API Client — unified HTTP + error handling
// ============================================

/** Lightweight toast via DOM — no framework dependency */
let toastContainer: HTMLDivElement | null = null

function ensureToastContainer(): HTMLDivElement {
  if (toastContainer) return toastContainer
  toastContainer = document.createElement('div')
  toastContainer.className = 'toast-container'
  document.body.appendChild(toastContainer)
  return toastContainer
}

function showToast(message: string, type: 'error' | 'success' | 'info' = 'error'): void {
  const container = ensureToastContainer()
  const el = document.createElement('div')
  el.className = `toast-item toast-${type}`
  el.textContent = message
  container.appendChild(el)
  setTimeout(() => {
    el.remove()
    if (container.children.length === 0) {
      container.remove()
      toastContainer = null
    }
  }, 4000)
}

/** Extract human-readable error message from AxiosError */
function extractErrorMessage(err: AxiosError): string {
  if (err.response?.data) {
    const data = err.response.data as Record<string, unknown>
    return String(data.detail ?? data.message ?? data.error ?? `请求失败 (${err.response.status})`)
  }
  if (err.code === 'ECONNABORTED') return '请求超时，请检查网络连接'
  if (err.code === 'ERR_NETWORK') return '无法连接到服务器'
  return err.message || '未知网络错误'
}

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL ? `${import.meta.env.VITE_API_URL}/api/v1` : '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// 请求拦截：自动带 token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：统一错误处理 + Toast
apiClient.interceptors.response.use(
  (res) => res,
  (err: AxiosError) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
      return Promise.reject(err)
    }
    // Skip toast for 404 on GET (not found is fine for browsing)
    if (!(err.response?.status === 404 && err.config?.method?.toLowerCase() === 'get')) {
      showToast(extractErrorMessage(err), 'error')
    }
    return Promise.reject(err)
  },
)

export { showToast }
export default apiClient
