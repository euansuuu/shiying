import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'com.example.videodownload',
  appName: '视频下载',
  webDir: 'dist',
  server: {
    androidScheme: 'https'
  }
}

export default config
