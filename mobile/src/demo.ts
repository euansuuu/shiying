import type { DownloadJob } from './types'

const now = new Date().toISOString()

export const demoJobs: DownloadJob[] = [
  {
    id: 'demo-travel',
    status: 'ready',
    progress: 100,
    title: '精彩旅行Vlog合集.mp4',
    author: '旅行记录',
    thumbnail_url: '/demo/travel.svg',
    duration: 86,
    size_bytes: 128 * 1024 * 1024,
    resolution: '1920×1080',
    extension: 'mp4',
    error_code: null,
    error_message: null,
    file_url: '#',
    created_at: now,
    updated_at: now
  },
  {
    id: 'demo-city',
    status: 'ready',
    progress: 100,
    title: '城市夜景延时摄影.mp4',
    author: '城市影像',
    thumbnail_url: '/demo/city.svg',
    duration: 142,
    size_bytes: 256 * 1024 * 1024,
    resolution: '3840×2160',
    extension: 'mp4',
    error_code: null,
    error_message: null,
    file_url: '#',
    created_at: now,
    updated_at: now
  }
]
