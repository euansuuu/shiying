from __future__ import annotations

import asyncio
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from yt_dlp.utils import DownloadError

from .config import settings
from .downloader import BrowserSessionError, InvalidLinkError, VideoDownloader
from .models import CreateJobRequest, HealthResponse, JobListResponse, JobResponse
from .repository import JobRepository


settings.data_dir.mkdir(parents=True, exist_ok=True)
downloads_dir = settings.data_dir / "downloads"
downloads_dir.mkdir(parents=True, exist_ok=True)
repository = JobRepository(settings.data_dir / "jobs.sqlite3")
downloader = VideoDownloader(settings)
semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
running_tasks: set[asyncio.Task[None]] = set()


def _to_response(job: dict) -> JobResponse:
    file_url = f"/api/v1/jobs/{job['id']}/file" if job["status"] == "ready" else None
    return JobResponse(**job, file_url=file_url)


def _classify_error(exc: BaseException) -> tuple[str, str]:
    message = str(exc)
    lower = message.lower()
    if isinstance(exc, InvalidLinkError):
        return "INVALID_LINK", message
    if isinstance(exc, BrowserSessionError):
        return "RISK_CONTROL", message
    if "unsupported url" in lower or "not found" in lower:
        return "VIDEO_UNAVAILABLE", "视频不存在、已删除或暂不支持"
    if "fresh cookies" in lower or "cookies" in lower:
        return "RISK_CONTROL", "抖音风控拦截，请稍后重试"
    return "DOWNLOAD_FAILED", message[-500:]


async def _run_job(job_id: str) -> None:
    async with semaphore:
        job = repository.get(job_id)
        job_dir = downloads_dir / job_id

        def report(status: str, progress: int) -> None:
            repository.update(job_id, status=status, progress=progress)

        try:
            result = await asyncio.to_thread(
                downloader.download,
                job["share_text"],
                job["quality"],
                job_dir,
                report,
            )
            repository.update(
                job_id,
                status="ready",
                progress=100,
                title=result.title,
                author=result.author,
                thumbnail_url=result.thumbnail_url,
                duration=result.duration,
                size_bytes=result.path.stat().st_size,
                resolution=result.resolution,
                extension=result.extension,
                file_path=str(result.path.resolve()),
                error_code=None,
                error_message=None,
            )
        except (InvalidLinkError, BrowserSessionError, DownloadError, RuntimeError) as exc:
            code, message = _classify_error(exc)
            repository.update(
                job_id,
                status="failed",
                error_code=code,
                error_message=message,
            )


def _schedule(job_id: str) -> None:
    task = asyncio.create_task(_run_job(job_id))
    running_tasks.add(task)
    task.add_done_callback(running_tasks.discard)


@asynccontextmanager
async def lifespan(_: FastAPI):
    repository.fail_interrupted_jobs()
    yield
    if running_tasks:
        await asyncio.gather(*running_tasks, return_exceptions=True)


app = FastAPI(title="视频下载服务", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/v1/jobs", response_model=JobResponse, status_code=201)
async def create_job(payload: CreateJobRequest) -> JobResponse:
    job = repository.create(payload.share_text, payload.quality)
    _schedule(job["id"])
    return _to_response(job)


@app.get("/api/v1/jobs", response_model=JobListResponse)
def list_jobs(limit: int = Query(default=30, ge=1, le=100)) -> JobListResponse:
    return JobListResponse(items=[_to_response(job) for job in repository.list(limit)])


@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    try:
        return _to_response(repository.get(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc


@app.get("/api/v1/jobs/{job_id}/file")
def download_file(job_id: str) -> FileResponse:
    try:
        job = repository.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc
    if job["status"] != "ready" or not job["file_path"]:
        raise HTTPException(status_code=409, detail="文件尚未准备完成")
    path = Path(job["file_path"])
    if not path.is_file() or downloads_dir.resolve() not in path.resolve().parents:
        raise HTTPException(status_code=404, detail="文件不存在")
    filename = f"{job['title'] or job_id}.{job['extension'] or 'mp4'}"
    return FileResponse(path, filename=filename, media_type="video/mp4")


@app.delete("/api/v1/jobs/{job_id}")
def delete_job(job_id: str) -> dict[str, bool]:
    try:
        job = repository.delete(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc
    if job.get("file_path"):
        job_dir = Path(job["file_path"]).parent
        if downloads_dir.resolve() in job_dir.resolve().parents:
            shutil.rmtree(job_dir, ignore_errors=True)
    return {"deleted": True}
