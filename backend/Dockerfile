FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    BROWSER_PROFILE_DIR=/data/browser-profile \
    BROWSER_HEADLESS=true

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY douyin_downloader.py /app/douyin_downloader.py
COPY backend /app/backend

EXPOSE 8000

CMD ["xvfb-run", "-a", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
