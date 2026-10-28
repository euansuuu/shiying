from __future__ import annotations

import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


class JobRepository:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS download_jobs (
                    id TEXT PRIMARY KEY,
                    share_text TEXT NOT NULL,
                    quality TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    title TEXT,
                    author TEXT,
                    thumbnail_url TEXT,
                    duration REAL,
                    size_bytes INTEGER,
                    resolution TEXT,
                    extension TEXT,
                    file_path TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def create(self, share_text: str, quality: str) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        job_id = uuid.uuid4().hex
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO download_jobs
                    (id, share_text, quality, status, progress, created_at, updated_at)
                VALUES (?, ?, ?, 'queued', 0, ?, ?)
                """,
                (job_id, share_text, quality, now, now),
            )
        return self.get(job_id)

    def update(self, job_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {
            "status", "progress", "title", "author", "thumbnail_url", "duration",
            "size_bytes", "resolution", "extension", "file_path", "error_code",
            "error_message",
        }
        values = {key: value for key, value in fields.items() if key in allowed}
        values["updated_at"] = datetime.now(UTC).isoformat()
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._lock, self._connect() as connection:
            connection.execute(
                f"UPDATE download_jobs SET {assignments} WHERE id = ?",
                (*values.values(), job_id),
            )
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM download_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return dict(row)

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM download_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def delete(self, job_id: str) -> dict[str, Any]:
        job = self.get(job_id)
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM download_jobs WHERE id = ?", (job_id,))
        return job

    def fail_interrupted_jobs(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE download_jobs
                SET status = 'failed', error_code = 'SERVER_RESTARTED',
                    error_message = '任务因服务重启中断，请重新提交',
                    updated_at = ?
                WHERE status IN ('queued', 'resolving', 'acquiring_session', 'downloading')
                """,
                (datetime.now(UTC).isoformat(),),
            )
