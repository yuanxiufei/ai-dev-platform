import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5175,
    proxy: {
      '/api': {
        target: 'http://localhost:18000',
        changeOrigin: true,
        ws: true,
        timeout: 600000,      // 10min — 代理连接超时
        proxyTimeout: 600000, // 10min — 代理响应超时（默认 30s 对大请求不够）
      },
    },
  },
})
