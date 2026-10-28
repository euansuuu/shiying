import { useCallback, useEffect, useMemo, useState } from 'react'
import { Clipboard, Search, Sun, X } from 'lucide-react'
import { createJob, deleteJob, listJobs } from './api'
import { JobCard } from './components/JobCard'
import { StatusBar } from './components/StatusBar'
import { demoJobs } from './demo'
import type { DownloadJob } from './types'

const activeStatuses = new Set(['queued', 'resolving', 'acquiring_session', 'downloading'])

function sharedTextFromUrl(): string {
  const params = new URLSearchParams(window.location.search)
  return [params.get('text'), params.get('url')].filter(Boolean).join(' ')
}

export default function App() {
  const demoMode = useMemo(() => new URLSearchParams(window.location.search).get('demo') === '1', [])
  const [shareText, setShareText] = useState(sharedTextFromUrl)
  const [jobs, setJobs] = useState<DownloadJob[]>(demoMode ? demoJobs : [])
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState('')
  const [settingsOpen, setSettingsOpen] = useState(false)

  const refresh = useCallback(async () => {
    if (demoMode) return
    try {
      setJobs(await listJobs())
      setMessage('')
    } catch {
      setMessage('无法连接远程服务，请检查服务地址')
    }
  }, [demoMode])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (demoMode || !jobs.some((job) => activeStatuses.has(job.status))) return
    const timer = window.setInterval(() => void refresh(), 1800)
    return () => window.clearInterval(timer)
  }, [demoMode, jobs, refresh])

  async function paste() {
    try {
      setShareText(await navigator.clipboard.readText())
      setMessage('')
    } catch {
      setMessage('无法读取剪贴板，请长按输入框粘贴')
    }
  }

  async function submit() {
    if (!shareText.trim()) {
      setMessage('请先粘贴抖音分享文本或链接')
      return
    }
    setSubmitting(true)
    setMessage('')
    try {
      const job = await createJob(shareText.trim())
      setJobs((current) => [job, ...current])
      setShareText('')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '提交失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  async function remove(id: string) {
    if (!demoMode) await deleteJob(id).catch(() => undefined)
    setJobs((current) => current.filter((job) => job.id !== id))
  }

  return (
    <main className="app-frame">
      <StatusBar />
      <div className="app-content">
        <header className="app-header">
          <h1>视频下载</h1>
          <button className="settings-button" onClick={() => setSettingsOpen(true)} aria-label="打开设置">
            <Sun size={19} strokeWidth={1.7} />
          </button>
        </header>

        <section className="link-panel" aria-labelledby="link-label">
          <label id="link-label" htmlFor="video-link">视频链接</label>
          <div className="input-row">
            <input
              id="video-link"
              value={shareText}
              onChange={(event) => setShareText(event.target.value)}
              placeholder="粘贴视频链接..."
              autoCapitalize="off"
              autoCorrect="off"
            />
            <button className="paste-button" onClick={paste} aria-label="从剪贴板粘贴">
              <Clipboard size={19} strokeWidth={1.8} />
            </button>
          </div>
        </section>

        <button className="parse-button" onClick={submit} disabled={submitting}>
          {submitting ? <span className="button-spinner" /> : <Search size={20} strokeWidth={2.1} />}
          <span>{submitting ? '正在提交' : '解析视频'}</span>
        </button>

        {message && <p className="inline-message">{message}</p>}

        <div className="divider" />

        <section className="downloads-section">
          <div className="section-heading">
            <h2>下载列表</h2>
            <span>{jobs.length} 个任务</span>
          </div>

          <div className="job-list">
            {jobs.map((job, index) => (
              <JobCard
                key={job.id}
                job={job}
                accent={index % 2 === 0 ? 'purple' : 'green'}
                onDelete={remove}
              />
            ))}
            {!jobs.length && (
              <div className="empty-state">
                <div className="empty-icon"><Search size={22} /></div>
                <p>还没有下载任务</p>
                <span>粘贴抖音分享链接开始解析</span>
              </div>
            )}
          </div>
        </section>
      </div>

      {settingsOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setSettingsOpen(false)}>
          <section className="settings-sheet" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="sheet-handle" />
            <div className="sheet-title">
              <h2>应用设置</h2>
              <button onClick={() => setSettingsOpen(false)} aria-label="关闭设置"><X size={20} /></button>
            </div>
            <div className="setting-row">
              <div><strong>下载画质</strong><span>由服务器选择最佳画质</span></div>
              <b>最佳</b>
            </div>
            <div className="setting-row">
              <div><strong>远程服务</strong><span>{import.meta.env.VITE_API_BASE_URL || '当前域名'}</span></div>
              <i className="online-dot" />
            </div>
          </section>
        </div>
      )}
    </main>
  )
}
