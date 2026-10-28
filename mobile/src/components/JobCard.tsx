import { Download, RefreshCw, Trash2 } from 'lucide-react'
import { apiUrl } from '../api'
import type { DownloadJob } from '../types'

interface Props {
  job: DownloadJob
  accent: 'purple' | 'green'
  onDelete: (id: string) => void
}

const statusText: Record<DownloadJob['status'], string> = {
  queued: '等待解析',
  resolving: '正在解析',
  acquiring_session: '获取浏览器会话',
  downloading: '正在下载',
  ready: '下载完成',
  failed: '解析失败'
}

function formatBytes(bytes: number | null): string {
  if (!bytes) return '大小计算中'
  const mb = bytes / 1024 / 1024
  return `${mb >= 100 ? mb.toFixed(0) : mb.toFixed(1)} MB`
}

export function JobCard({ job, accent, onDelete }: Props) {
  const ready = job.status === 'ready'
  const failed = job.status === 'failed'
  const fileName = job.title || statusText[job.status]
  const details = ready
    ? `${formatBytes(job.size_bytes)} · ${job.resolution || '自动分辨率'} · ${(job.extension || 'mp4').toUpperCase()}`
    : failed
      ? job.error_message || '请稍后重试'
      : `${statusText[job.status]} · ${job.progress}%`

  return (
    <article className={`job-card ${failed ? 'is-failed' : ''}`}>
      <div className="thumbnail-shell">
        {job.thumbnail_url ? (
          <img src={job.thumbnail_url} alt="" className="job-thumbnail" />
        ) : (
          <div className="thumbnail-fallback"><RefreshCw size={20} /></div>
        )}
        {!ready && !failed && <span className="progress-fill" style={{ width: `${job.progress}%` }} />}
      </div>
      <div className="job-copy">
        <h3>{fileName}</h3>
        <p>{details}</p>
      </div>
      {ready && job.file_url ? (
        <a
          className={`download-button ${accent}`}
          href={apiUrl(job.file_url)}
          download
          aria-label={`下载 ${fileName}`}
        >
          <Download size={20} strokeWidth={2.2} />
        </a>
      ) : failed ? (
        <button className="delete-button" onClick={() => onDelete(job.id)} aria-label="删除失败任务">
          <Trash2 size={18} />
        </button>
      ) : (
        <div className="job-spinner" aria-label={statusText[job.status]} />
      )}
    </article>
  )
}
