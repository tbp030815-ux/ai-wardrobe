import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 开发时把 /api 请求转发到 FastAPI 后端
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      // 衣物图片由后端静态目录提供（/uploads/xxx.png）
      '/uploads': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})