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

# ─── GigaAM: движок и веса ──────────────────────────────────────────────────
#
# Основной распознаватель с 20.08.2026 (docs/ASR_BAKEOFF_2026-08-20.md).
#
# ─── Почему --no-deps ─────────────────────────────────────────────────────
# Пакет закрепляет `onnxruntime==1.23.*`, а в образе 1.29 под sherpa-onnx.
# Обычная установка молча понизит его — и сломает parakeet, который до полного
# отказа от него остаётся исполнимым для перезапуска старых прогонов. Понижение
# не выглядит ошибкой: pip печатает предупреждение и продолжает.
#
# Поэтому зависимости перечислены руками. Torch и torchaudio уже стоят (CPU-сборка
# выше), soundfile тянется вместе с pyannote, остальное — четыре лёгких пакета.
#
# ─── Почему из архива, а не из PyPI ───────────────────────────────────────
# На PyPI лежит 0.1.0 — редакция v2, моделей v3 в ней нет. v3 живёт только в
# репозитории. Пин на коммит здесь был бы честнее ветки, но у проекта нет тегов
# релизов, и коммит пришлось бы обновлять вручную при каждом исправлении.
RUN pip install "hydra-core==1.3.*" "omegaconf==2.3.*" sentencepiece soundfile \
 && pip install --no-deps "https://github.com/salute-developers/GigaAM/archive/refs/heads/main.zip" \
 && python -c "\
import importlib.metadata as md, sys; \
v = md.version('onnxruntime'); \
sys.exit(0 if v.startswith('1.29') else sys.stderr.write( \
  'onnxruntime понижен до ' + v + ': GigaAM протащил свой пин мимо --no-deps, ' \
  'sherpa-onnx сломается на первом прогоне parakeet' + chr(10)) or 1)"

# Веса GigaAM в образ — по той же причине, что и веса parakeet ниже: скачивание
# посреди прогона выглядит случайно долгой транскрипцией, а не нехваткой модели.
#
# GIGAAM_HOME читает agent_core/asr/gigaam.py и передаёт в load_model как
# download_root. Каталог внутри образа, а не на томе: образ обязан быть
# самодостаточным.
ENV GIGAAM_HOME=/opt/models/gigaam
RUN mkdir -p /opt/models/gigaam \
 && python -c "\
import gigaam; \
gigaam.load_model('v3_e2e_rnnt', device='cpu', download_root='/opt/models/gigaam')" \
 && python -c "\
import pathlib, sys; \
files = list(pathlib.Path('/opt/models/gigaam').rglob('*')); \
weight = sum(f.stat().st_size for f in files if f.is_file()); \
sys.exit(0 if weight > 100 * 1024 * 1024 else sys.stderr.write( \
  'веса GigaAM не скачались: ' + str(weight) + ' байт' + chr(10)) or 1)"

# ─── Веса parakeet в образ ──────────────────────────────────────────────────
#
# 671 МБ int8-весов пекутся сюда намеренно. Скачивание модели посреди прогона —
# ровно тот дефект, который чинился для whisper (пункт 29 списка владельца): он
# не выглядит нехваткой модели, он выглядит случайно долгой транскрипцией в
# первый раз и нормальной во второй, то есть чинит себя сам и не воспроизводится,
# когда за него берутся.
#
# Каталог /opt/models, а не кэш HuggingFace на томе: том общий и переживает
# пересборку, и модель, оказавшаяся там, продолжала бы работать даже после того,
# как её убрали из образа. Образ обязан быть самодостаточным.
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8', \
                  local_dir='/opt/models/parakeet-tdt-0.6b-v3')" \
 && rm -rf /opt/models/parakeet-tdt-0.6b-v3/.cache \
 && python -c "\
import pathlib, sys; \
d = pathlib.Path('/opt/models/parakeet-tdt-0.6b-v3'); \
need = ['encoder.int8.onnx', 'decoder.int8.onnx', 'joiner.int8.onnx', 'tokens.txt']; \
missing = [n for n in need if not (d / n).exists()]; \
sys.exit(0 if not missing else sys.stderr.write('нет весов parakeet: ' + str(missing) + chr(10)) or 1)"

COPY services/agent-core/ ./
COPY packages/shared/ /app/shared/
COPY prompts/ /app/prompts/
# Корпус заземления. Без него генерация аудитории в воркере падает с
# FileNotFoundError: раньше её запускал веб, и в образ она не попадала.
COPY data/ /app/data/

RUN pip install -e .

# Непривилегированный пользователь.
#
# Кэш моделей обязан лежать в его домашнем каталоге, а не в /root: том с весами
# монтируется снаружи, и процесс под uid 1001 в /root (режим 700) писать не может.
# Проявилось бы это не при сборке, а на первой транскрипции — отказом в доступе
# посреди прогона, уже после загрузки видео.
RUN useradd --create-home --uid 1001 celeryuser \
    && mkdir -p /home/celeryuser/.cache/huggingface \
    && chown -R celeryuser:celeryuser /app /home/celeryuser /opt/models
USER celeryuser

CMD ["celery", "-A", "agent_core.celery_app", "worker", "--loglevel=info"]
