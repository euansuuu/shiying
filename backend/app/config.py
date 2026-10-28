from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    browser_profile_dir: Path
    browser_headless: bool
    browser_channel: str | None
    cors_origins: tuple[str, ...]
    max_concurrent_jobs: int

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("DATA_DIR", "./data")).expanduser().resolve()
        profile_dir = Path(
            os.getenv("BROWSER_PROFILE_DIR", str(data_dir / "browser-profile"))
        ).expanduser().resolve()
        origins = tuple(
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        )
        return cls(
            data_dir=data_dir,
            browser_profile_dir=profile_dir,
            browser_headless=_as_bool(os.getenv("BROWSER_HEADLESS"), True),
            browser_channel=os.getenv("BROWSER_CHANNEL") or None,
            cors_origins=origins,
            max_concurrent_jobs=max(1, int(os.getenv("MAX_CONCURRENT_JOBS", "1"))),
        )


settings = Settings.from_env()
