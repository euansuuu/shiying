import type { DownloadJob } from './types'

const configuredBase = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''

export function apiUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path
  return `${configuredBase}${path}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers
    }
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

export async function listJobs(): Promise<DownloadJob[]> {
  const result = await request<{ items: DownloadJob[] }>('/api/v1/jobs')
  return result.items
}

export function createJob(shareText: string): Promise<DownloadJob> {
  return request<DownloadJob>('/api/v1/jobs', {
    method: 'POST',
    body: JSON.stringify({ share_text: shareText, quality: 'best' })
  })
}

export function deleteJob(id: string): Promise<void> {
  return fetch(apiUrl(`/api/v1/jobs/${id}`), { method: 'DELETE' }).then((response) => {
    if (!response.ok) throw new Error('删除任务失败')
  })
}
