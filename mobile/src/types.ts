export type JobStatus =
  | 'queued'
  | 'resolving'
  | 'acquiring_session'
  | 'downloading'
  | 'ready'
  | 'failed'

export interface DownloadJob {
  id: string
  status: JobStatus
  progress: number
  title: string | null
  author: string | null
  thumbnail_url: string | null
  duration: number | null
  size_bytes: number | null
  resolution: string | null
  extension: string | null
  error_code: string | null
  error_message: string | null
  file_url: string | null
  created_at: string
  updated_at: string
}
