import { useEffect, useState } from 'react'
import { ArrowLeft, ArrowRight, Bell, Check, CheckCircle2, ChevronRight, Clipboard, Copy, Download, FileText, FolderHeart, FolderOutput, ImageDown, ImageOff, Images, Info, Moon, Plus, RotateCw, Settings2, LoaderCircle, Smartphone, Sun, Trash2, Video, X, Monitor } from 'lucide-react'
import { isAndroid, Local, localImage } from './native'
import type { Job, Snapshot, Theme } from './types'

const labels: Record<string, string> = { queued: '等待中', resolving: '解析中', verification: '需要验证', downloading: '下载中', completed: '已完成', partial: '部分完成', failed: '下载失败', cancelled: '已取消', interrupted: '已中断', deferred: '稍后处理' }
const active = new Set(['queued', 'resolving', 'downloading'])
const initial: Snapshot = { jobs: [], theme: 'system', remember: true, sharedText: '' }
function size(value: number) { return value >= 1073741824 ? `${(value / 1073741824).toFixed(2)} GB` : value >= 1048576 ? `${(value / 1048576).toFixed(1)} MB` : `${Math.round(value / 1024)} KB` }
function status(job: Job) {
  if (job.kind === 'album' && job.total) return `${labels[job.status]} · 已保存 ${job.done}/${job.total} 张${job.status === 'completed' ? ' · ' + size(job.bytes) : ''}`
  if (job.status === 'downloading' && job.currentTotal) return `下载中 · ${Math.min(99, Math.floor(job.currentBytes * 100 / job.currentTotal))}%`
  return `${labels[job.status] ?? job.status}${job.status === 'completed' ? ' · ' + size(job.bytes) : ''}`
}
function Caption({ job }: { job: Job }) {
  return <span className={`job-status ${job.status === 'partial' ? 'warn' : job.status === 'completed' ? 'success' : ''}`}>{status(job)}</span>
}
function Cover({ job }: { job: Job }) {
  const image = localImage(job.thumbnail)
  return <span className="cover">{image ? <img src={image} alt="已保存作品的缩略图" /> : job.kind === 'album' ? <Images /> : <Video />}{job.kind === 'album' && job.total > 0 ? <span className="cover-count">{job.total} 张</span> : null}</span>
}

function JobCard({ item, detail, taskAction, retryLabel }: { item: Job; detail: (job: Job) => void; taskAction: (job: Job, action: "cancel" | "retry" | "open" | "export") => Promise<void>; retryLabel: (job: Job) => string }) {
    return <article className="job-card"><div className="job-main"><button className="cover-button" onClick={() => detail(item)} aria-label="查看任务详情"><Cover job={item} /></button><div className="job-info"><button className="job-title" onClick={() => detail(item)}>{item.title}</button><p className="meta">{[item.author, item.kind === 'album' ? '图文' : item.kind === 'video' ? '视频' : '待识别'].filter(Boolean).join(' · ')}</p><div className="row"><Caption job={item} />{active.has(item.status) ? <button className="icon-button" onClick={() => void taskAction(item, 'cancel')} aria-label="取消任务"><X size={18} /></button> : item.status !== 'completed' ? <button className="mini-button" onClick={() => void taskAction(item, 'retry')}>{retryLabel(item)}</button> : <button className="mini-button" onClick={() => item.kind === 'album' ? detail(item) : void taskAction(item, 'open')}>查看</button>}</div></div></div>{item.status === 'downloading' ? <><div className="track" role="progressbar" aria-label="下载进度" aria-valuenow={item.kind === 'album' ? item.done : item.currentBytes} aria-valuemin={0} aria-valuemax={item.kind === 'album' ? item.total : item.currentTotal || undefined}><span style={{ width: `${item.kind === 'album' ? item.done * 100 / Math.max(1, item.total) : item.currentTotal ? Math.min(99, item.currentBytes * 100 / item.currentTotal) : 0}%` }} /></div><div className="job-foot"><span>{item.kind === 'album' ? `当前第 ${item.current} 张 · ` : ''}{size(item.currentBytes)}{item.currentTotal ? ' / ' + size(item.currentTotal) : ''}</span><span>{size(item.speed)}/s</span></div></> : null}{item.status === 'resolving' ? <div className="parsing-state" role="status"><LoaderCircle size={17} aria-hidden="true" /><span>{item.message || '正在本机识别作品…'}</span></div> : null}{item.message && ['failed', 'partial', 'interrupted', 'cancelled', 'deferred', 'verification'].includes(item.status) ? <p className="job-message">{item.message}</p> : null}</article>
  }

export default function App() {
  const [data, setData] = useState<Snapshot>(initial)
  const [view, setView] = useState<'home' | 'records' | 'settings' | 'detail'>('home')
  const [selected, setSelected] = useState('')
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState('all')
  const [imageLimit, setImageLimit] = useState(24)
  const [dialog, setDialog] = useState<{ title: string; description: string; confirm?: () => void } | null>(null)

  useEffect(() => {
    if (!isAndroid) { setError('请在拾影安卓 APK 中使用。本页面不连接远程下载服务。'); return }
    let disposed = false
    const subscriptions = [
      Local.addListener('changed', (snapshot) => { if (!disposed) setData(snapshot) }),
      Local.addListener('shared', (event) => { if (!disposed) { setText(event.text); setView('home') } }),
    ]
    void Promise.all(subscriptions).then(() => Local.snapshot()).then(snapshot => {
      if (!disposed) { setData(snapshot); if (snapshot.sharedText) setText(snapshot.sharedText) }
    }).catch(() => { if (!disposed) setError('无法读取本地数据，请重新打开拾影。') })
    return () => { disposed = true; for (const subscription of subscriptions) void subscription.then(item => item.remove()) }
  }, [])
  useEffect(() => {
    document.documentElement.dataset.theme = data.theme
    document.documentElement.style.colorScheme = data.theme === 'system' ? 'light dark' : data.theme
  }, [data.theme])
  useEffect(() => { if (!toast) return; const timer = window.setTimeout(() => setToast(''), 3300); return () => clearTimeout(timer) }, [toast])
  const job = data.jobs.find(item => item.id === selected)
  const history = data.jobs.filter(item => item.status === 'completed' || item.done > 0 && !active.has(item.status))
  function detail(item: Job) { setSelected(item.id); setImageLimit(24); setView('detail') }
  async function run(action: () => Promise<unknown>, success?: string) {
    try { await action(); if (success) setToast(success) }
    catch (cause) { setToast(cause instanceof Error ? cause.message : '操作未完成，请重试。') }
  }
  function taskAction(item: Job, action: 'cancel' | 'retry' | 'open' | 'export') {
    return run(() => Local.action({ id: item.id, action }))
  }
  async function submit() {
    if (!text.trim()) { setError('请先粘贴抖音分享文字或链接'); return }
    if (!isAndroid) return
    setBusy(true); setError('')
    try { await Local.add({ text: text.trim() }); setText('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : '无法添加下载任务') }
    finally { setBusy(false) }
  }
  function retryLabel(item: Job) { return item.kind === 'album' && item.done > 0 ? item.status === 'partial' ? '重试失败项' : '继续下载' : '重新下载' }
  const settingTheme = (theme: Theme) => void run(() => Local.preferences({ theme }))
  return <div className="app"><header className="header">{view === 'detail' ? <div className="back-heading"><button className="icon-button" onClick={() => setView('home')} aria-label="返回下载任务"><ArrowLeft /></button><h1>作品详情</h1></div> : view === 'home' ? <><div className="brand"><img src="brand.png" alt="拾影图标" /><h1>拾影</h1></div><span className="local"><Smartphone size={15} />本地下载</span></> : <><h1>{view === 'records' ? '下载记录' : '设置'}</h1><img className="small-brand" src="brand.png" alt="拾影" /></>}</header>
    <main className="content">
      {view === 'home' ? <><p className="lead">视频与图文，存进你的手机。</p><section className="composer"><div className="row"><label htmlFor="share">抖音分享链接</label><button className="link-button" onClick={() => void run(async () => { const clip = await Local.paste(); setText(clip.text); setError('') })}><Clipboard size={17} />粘贴</button></div><textarea id="share" value={text} onChange={event => setText(event.target.value)} placeholder={'粘贴完整分享文字或链接…\n自动识别视频与图文'} /><div className="input-error" role="alert">{error}</div><button className="primary" onClick={() => void submit()} disabled={busy || !isAndroid}><Plus />{busy ? '正在添加…' : '解析并下载'}</button><div className="save-hint"><ImageDown size={15} />保存到手机相册</div></section><div className="section-heading"><h2>下载任务</h2><span>顺序下载 · {data.jobs.length} 个任务</span></div><div className="job-list">{data.jobs.length ? data.jobs.map(item => <JobCard key={item.id} item={item} detail={detail} taskAction={taskAction} retryLabel={retryLabel} />) : <div className="empty"><Download size={30} /><strong>还没有下载任务</strong><p>粘贴分享链接，或从系统分享面板<br />把作品发送给拾影。</p></div>}</div><p className="note"><Smartphone size={15} />文件与记录保存在这台手机</p></> : null}
      {view === 'records' ? <><p className="lead">已经保存的喜欢，随时回来看看。</p><div className="filters" aria-label="记录类型">{[['all', '全部'], ['video', '视频'], ['album', '图文']].map(([key, name]) => <button key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}>{name}</button>)}</div><div className="job-list">{history.filter(item => filter === 'all' || item.kind === filter).map(item => <JobCard key={item.id} item={item} detail={detail} taskAction={taskAction} retryLabel={retryLabel} />)}{!history.some(item => filter === 'all' || item.kind === filter) ? <div className="empty"><FolderHeart size={30} /><strong>还没有已保存的作品</strong><p>完成下载后，作品会出现在这里。</p></div> : null}</div></> : null}
      {view === 'settings' ? <><p className="lead">让拾影，符合你的习惯。</p><p className="group-title">外观</p><section className="setting-group appearance"><div className="theme-picker">{([['light', '浅色', Sun], ['dark', '暗色', Moon], ['system', '跟随系统', Monitor]] as const).map(([key, name, Icon]) => <button key={key} aria-pressed={data.theme === key} onClick={() => settingTheme(key)}><Icon size={16} />{name}</button>)}</div><p>立即生效，并记住本机选择</p></section><p className="group-title">保存与通知</p><section className="setting-group"><div className="setting-row"><div><strong>视频与图片</strong><small>默认保存到手机相册</small></div><Images /></div><button className="setting-row setting-button" onClick={() => void run(() => Local.notifications())}><div><strong>下载通知</strong><small>在通知栏查看进度与取消任务</small></div><ChevronRight /></button></section><p className="group-title">解析会话</p><section className="setting-group"><div className="setting-row"><div><strong>保留解析会话</strong><small>{data.remember ? '仅保存在本应用内，便于下次解析' : '任务结束及下次启动时清除'}</small></div><button className="switch" role="switch" aria-label="保留解析会话" aria-checked={data.remember} onClick={() => void run(() => Local.preferences({ remember: !data.remember }))}><span /></button></div><button className="setting-row setting-button" onClick={() => setDialog({ title: '清除解析会话？', description: '清除拾影保存的解析会话。已下载文件与任务记录会保留。', confirm: () => void run(() => Local.clearSession(), '解析会话已清除。') })}><div><strong>清除解析会话</strong><small>移除拾影内部保存的解析会话</small></div><Trash2 size={19} /></button></section><div className="settings-footer"><strong>拾影 Android · 0.1.5</strong><span>本地下载 · 不需要解析服务器</span><small>仅保存你有权使用的内容</small></div></> : null}
      {view === 'detail' && job ? <><h2 className="detail-title">{job.title}</h2><p className="meta">{job.author || '未知作者'} · {job.kind === 'album' ? `图文 · ${job.total} 张图片` : job.kind === 'video' ? '视频' : '待识别作品'}</p>{job.kind === 'video' && job.thumbnail ? <img className="detail-cover" src={localImage(job.thumbnail)} alt="已保存视频的封面" /> : null}<div className={`alert ${job.status === 'completed' ? 'complete' : ''}`} role="status">{job.status === 'completed' ? <CheckCircle2 /> : job.status === 'resolving' ? <LoaderCircle className="spinning" /> : <Info />}<div><strong>{status(job)}</strong><p>{job.message || (job.kind === 'album' ? '已保存的图片会保留，重试只处理未完成项。' : '文件将保存至手机相册。')}</p></div></div>{job.kind === 'album' ? <><div className="row"><strong>作品图片</strong><span className="meta">按原顺序保存</span></div><div className="image-grid">{job.assets.slice(0, imageLimit).map(asset => <div className={`image-item ${asset.status !== 'completed' ? 'image-missing' : ''}`} key={asset.index}>{asset.status === 'completed' && asset.thumbnail ? <><img src={localImage(asset.thumbnail)} alt={`第 ${asset.index} 张已保存图片`} /><span className="saved"><Check size={13} /></span></> : <><ImageOff /><span>第 {asset.index} 张{asset.status === 'failed' ? '未完成' : '待保存'}</span></>}<span className="image-number">{String(asset.index).padStart(3, '0')}</span></div>)}</div>{job.assets.length > imageLimit ? <button className="secondary" onClick={() => setImageLimit(value => value + 24)}>查看更多图片</button> : null}</> : null}{job.caption ? <section className="text-block"><div className="row"><strong>作品文案</strong><button className="link-button" onClick={() => void run(() => Local.copyCaption({ id: job.id }), '文案已复制。')}><Copy size={17} />复制</button></div><p>{job.caption}</p></section> : null}{job.notice ? <p className="caption-info">{job.notice}</p> : null}{job.failed > 0 || job.assets.some(asset => asset.error) ? <button className="link-button" onClick={() => setDialog({ title: '未完成项', description: job.assets.filter(asset => asset.status !== 'completed').map(asset => `第 ${asset.index} 项：${asset.error || '尚未保存'}`).join('\n') || job.message })}><Info size={17} />查看失败原因</button> : null}<div className="bottom-actions">{job.status === 'completed' ? <button className="primary" onClick={() => void taskAction(job, 'open')}><Images />{job.kind === 'album' ? '查看手机相册' : '打开视频'}</button> : active.has(job.status) ? <button className="secondary" onClick={() => void taskAction(job, 'cancel')}><X size={18} />取消任务</button> : <button className="primary" onClick={() => void taskAction(job, 'retry')}><RotateCw size={18} />{retryLabel(job)}</button>}{job.done > 0 ? <button className="secondary" onClick={() => void taskAction(job, 'export')}><FolderOutput size={18} />导出文件与文案</button> : null}</div>{job.status === 'completed' && job.kind === 'video' ? <button className="link-button" onClick={() => void taskAction(job, 'retry')}><RotateCw size={17} />重新下载</button> : null}</> : null}
    </main>
    {view !== 'detail' ? <nav className="bottom-nav" aria-label="底部导航">{([['home', '下载', Download], ['records', '记录', FolderHeart], ['settings', '设置', Settings2]] as const).map(([key, name, Icon]) => <button key={key} aria-current={view === key ? 'page' : undefined} onClick={() => setView(key)}><span><Icon size={21} /></span>{name}</button>)}</nav> : null}
    {toast ? <div className="toast" role="status">{toast}</div> : null}
    {dialog ? <div className="overlay" onClick={() => setDialog(null)}><section className="sheet" role="dialog" aria-modal="true" aria-label={dialog.title} onClick={event => event.stopPropagation()}><h2>{dialog.title}</h2><p>{dialog.description}</p>{dialog.confirm ? <button className="primary" onClick={() => { dialog.confirm?.(); setDialog(null) }}>确认</button> : null}<button className="secondary" onClick={() => setDialog(null)}>返回</button></section></div> : null}
  </div>
}
