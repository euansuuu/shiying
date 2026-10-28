from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    resolving = "resolving"
    acquiring_session = "acquiring_session"
    downloading = "downloading"
    ready = "ready"
    failed = "failed"


class CreateJobRequest(BaseModel):
    share_text: str = Field(min_length=10, max_length=4000)
    quality: str = Field(default="best", pattern="^(best|1080p|720p)$")


class JobResponse(BaseModel):
    id: str
    status: JobStatus
    progress: int
    title: str | None = None
    author: str | None = None
    thumbnail_url: str | None = None
    duration: float | None = None
    size_bytes: int | None = None
    resolution: str | None = None
    extension: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    file_url: str | None = None
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[JobResponse]


class HealthResponse(BaseModel):
    status: str
