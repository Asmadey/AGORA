# services/agent-core — FastAPI + Celery + LangGraph (Python 3.13, PRD §15).
# CPU-only: модели рассуждения ходят по API (Qwen через timeweb), локально крутятся
# только Whisper и pyannote. GPU не нужен — Decision Log #1.
# syntax=docker/dockerfile:1

FROM python:3.13-slim AS base

# ffmpeg — обязателен для задачи #14 (extract_audio, сегментация длинного видео)
#          и для torchcodec, которым pyannote.audio 4.x декодирует аудио.
# libgomp1 — нужен faster-whisper (CTranslate2) для многопоточности на CPU.
# libsndfile1 — чтение wav в soundfile/pyannote.
# espeak-ng — синтез речи для фикстур CDD-теста #15. Транскрипт и диаризацию
#   нельзя проверить на синтетическом тоне: нужна настоящая речь. Хранить в git
#   записанный голос — это и вес, и вопрос о правах на запись; сгенерированная
#   речь воспроизводима одной командой и не тянет ни того, ни другого.
#   Пакет весит меньше мегабайта.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgomp1 \
        libsndfile1 \
        curl \
        espeak-ng \
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

# torch ставится ПЕРВЫМ и из CPU-индекса. Иначе pyannote.audio притянет его с
# обычного PyPI, а там сборка с CUDA: +2,5 ГБ образа и десяток библиотек NVIDIA,
# которые на машине без видеокарты не нужны и не используются (GPU нет —
# Decision Log #1). Проверено на первой сборке: приехал torch 2.13.0+cu130.
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch torchaudio

RUN pip install -e ".[dev]" || pip install --upgrade pip

# Проверка сборки opencv — на этапе сборки, а не при первом импорте на проде.
#
# scenedetect тянет opencv, и сборок две. Headless работает в python:3.13-slim
# как есть; полная (opencv-python) линкуется с libGL.so.1, которого в slim нет,
# и падает при импорте — то есть посреди задачи #16, через минуты после старта
# прогона, уже после транскрипции.
#
# Соблазн «поставить libGL и не думать» решает симптом ценой смысла: GUI-сборка
# тянет GTK и X11 в контейнер, которому нечего показывать, и следующий, кто
# увидит libgl1 в списке пакетов, не сможет понять, зачем он здесь.
#
# Поэтому здесь стоит утверждение, а не пакет. Спек в pyproject закреплён
# `scenedetect[opencv-headless]>=0.6.4,<0.7`, но на 0.7.x pip печатает
# «does not provide the extra» и тихо ставит полную сборку — предупреждением,
# не ошибкой. Эта строка превращает предупреждение в отказ сборки.
RUN python -c "import importlib.metadata as md, sys; \
names = {d.metadata['Name'] for d in md.distributions()}; \
gui = 'opencv-python' in names; \
ok = 'opencv-python-headless' in names and not gui; \
sys.stderr.write('opencv: стоит ' + ('opencv-python (GUI)' if gui else 'НИ ОДНОЙ сборки') + \
  '. В python:3.13-slim нет libGL.so.1 — воркер упадёт при импорте scenedetect, ' + \
  'посреди задачи #16. Обычная причина: снят потолок scenedetect<0.7, а в 0.7.x ' + \
  'экстру opencv-headless убрали и pip тихо ставит GUI-сборку.\n') if not ok else None; \
sys.exit(0 if ok else 1)"

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
