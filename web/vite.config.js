import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const host = process.env.VITE_HOST || '127.0.0.1'
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8765'

export default defineConfig({
  plugins: [react()],
  server: {
    host,
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': apiProxyTarget,
    },
  },
})
