import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['app-icon.svg'],
      manifest: {
        name: '视频下载',
        short_name: '视频下载',
        description: '解析并下载抖音分享视频',
        theme_color: '#ffffff',
        background_color: '#f8f8fb',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        icons: [
          {
            src: '/app-icon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any maskable'
          }
        ],
        share_target: {
          action: '/',
          method: 'GET',
          params: { title: 'title', text: 'text', url: 'url' }
        }
      }
    })
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000'
    }
  }
})
