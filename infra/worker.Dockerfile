# services/agent-core — FastAPI + Celery + LangGraph (Python 3.13, PRD §15).
# CPU-only: модели рассуждения ходят по API (Qwen через timeweb), локально крутятся
# только Whisper и pyannote. GPU не нужен — Decision Log #1.
# syntax=docker/dockerfile:1

FROM python:3.13-slim AS base

# ffmpeg — обязателен для задачи #14 (extract_audio, сегментация длинного видео)
#          и для torchcodec, которым pyannote.audio 4.x декодирует аудио.
# libgomp1 — нужен faster-whisper (CTranslate2) для многопоточности на CPU.
# libsndfile1 — чтение wav в soundfile/pyannote.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgomp1 \
        libsndfile1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# HF_HOME — кэш весов Whisper и pyannote на смонтированном томе. Модели тяжёлые,
#   качать их при каждом старте и медленно, и хрупко: если из сети развёртывания
#   нет доступа к Hugging Face, воркер не поднимется вообще.
# PYANNOTE_METRICS_ENABLED — pyannote 4.x по умолчанию шлёт статистику вызовов
#   наружу. Продукт продаётся как self-host, исходящий трафик должен быть явным.
# OMP_NUM_THREADS — иначе каждый из четырёх процессов Celery заберёт все ядра,
#   и на CPU-инференсе они начнут конкурировать друг с другом, а не считать.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/celeryuser/.cache/huggingface \
    PYANNOTE_METRICS_ENABLED=0 \
    OMP_NUM_THREADS=4

WORKDIR /app

# Слой зависимостей отдельно от кода — пересборка при правке кода не тянет pip заново.
COPY services/agent-core/pyproject.toml ./
RUN pip install --upgrade pip && pip install -e ".[dev]" || pip install --upgrade pip

COPY services/agent-core/ ./
COPY packages/shared/ /app/shared/
COPY prompts/ /app/prompts/

RUN pip install -e .

# Непривилегированный пользователь.
#
# Кэш моделей обязан лежать в его домашнем каталоге, а не в /root: том с весами
# монтируется снаружи, и процесс под uid 1001 в /root (режим 700) писать не может.
# Проявилось бы это не при сборке, а на первой транскрипции — отказом в доступе
# посреди прогона, уже после загрузки видео.
RUN useradd --create-home --uid 1001 celeryuser \
    && mkdir -p /home/celeryuser/.cache/huggingface \
    && chown -R celeryuser:celeryuser /app /home/celeryuser
USER celeryuser

CMD ["celery", "-A", "agent_core.celery_app", "worker", "--loglevel=info"]
