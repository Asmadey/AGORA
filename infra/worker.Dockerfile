# services/agent-core — FastAPI + Celery + LangGraph (Python 3.13, PRD §15).
# CPU-only: модели рассуждения ходят по API (Qwen через timeweb), локально крутятся
# только Whisper и pyannote. GPU не нужен — Decision Log #1.
# syntax=docker/dockerfile:1

FROM python:3.13-slim AS base

# ffmpeg — обязателен для задачи #14 (extract_audio, сегментация длинного видео).
# libgomp1 — нужен faster-whisper (CTranslate2) для многопоточности на CPU.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Слой зависимостей отдельно от кода — пересборка при правке кода не тянет pip заново.
COPY services/agent-core/pyproject.toml ./
RUN pip install --upgrade pip && pip install -e ".[dev]" || pip install --upgrade pip

COPY services/agent-core/ ./
COPY packages/shared/ /app/shared/
COPY prompts/ /app/prompts/

RUN pip install -e .

# Непривилегированный пользователь.
RUN useradd --create-home --uid 1001 celeryuser && chown -R celeryuser:celeryuser /app
USER celeryuser

CMD ["celery", "-A", "agent_core.celery_app", "worker", "--loglevel=info"]
