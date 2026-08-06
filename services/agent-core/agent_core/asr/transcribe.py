"""
Транскрипция и детекция речи (задача #15).

faster-whisper — реализация Whisper на CTranslate2. Выбрана не за скорость саму
по себе, а потому что считает на CPU за разумное время: GPU в развёртывании нет
(Decision Log #1), а оригинальный whisper на процессоре непригоден для роликов
длиннее пары минут.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_MODEL = "large-v3"
DEFAULT_COMPUTE_TYPE = "int8"


@dataclass(frozen=True)
class Segment:
    """Кусок транскрипта с таймкодами в секундах от начала дорожки."""

    start: float
    end: float
    text: str


@lru_cache(maxsize=2)
def _model(name: str, compute_type: str):
    """
    Загруженная модель. Кеш обязателен, а не оптимизация.

    Без него каждый вызов задачи Celery поднимал бы large-v3 заново: это минуты
    на задачу и, при четырёх процессах prefork, четыре копии модели в памяти —
    гарантированный OOM на машине с 8 ГБ. Ключ кеша — имя и тип вычислений,
    чтобы смена модели из Настроек (#27) не отдавала старую.

    Импорт внутри функции намеренно: faster-whisper тянет CTranslate2 и модель
    целиком, и делать это при импорте модуля значит платить за них даже там, где
    транскрипция не нужна — например, в статическом уровне CDD-теста.

    ─── Почему download_root не передаётся ──────────────────────────────────
    Раньше сюда уходило `download_root=HF_HOME`. Параметр отдаётся в
    huggingface_hub как `cache_dir`, то есть заменяет собой корень кэша целиком,
    а не задаёт его родителя: модели ложились в `$HF_HOME/models--Systran--*`,
    тогда как всё остальное (pyannote, любой другой вызов hub) читает и пишет в
    `$HF_HOME/hub/`. В одном томе получалось два кэша.

    Само по себе это работало и потому было незаметно. Ломается оно при первом
    же взгляде со стороны: `try_to_load_from_cache` смотрит в стандартный корень,
    отвечает «модели нет» — и вывод «воркер скачает 2.9 ГБ заново» выглядит
    обоснованным, хотя модель на диске есть. Мы на этом уже потеряли проход.

    Без параметра действует HF_HOME, и оба каталога сходятся в `$HF_HOME/hub/`.
    """
    from faster_whisper import WhisperModel

    return WhisperModel(name, device="cpu", compute_type=compute_type)


def _settings() -> tuple[str, str]:
    return (
        os.environ.get("WHISPER_MODEL", DEFAULT_MODEL),
        os.environ.get("WHISPER_COMPUTE_TYPE", DEFAULT_COMPUTE_TYPE),
    )


def transcribe(
    audio: str | Path,
    language: str | None = None,
    vad: bool = True,
) -> list[Segment]:
    """
    Речь в текст с таймкодами.

    `vad=True` отбрасывает тишину до распознавания. Это не только экономия:
    Whisper на длинной тишине склонен галлюцинировать — выдавать фразы, которых
    в записи нет. Такие вставки неотличимы от настоящего текста и портят всё, что
    строится дальше на транскрипте.

    `language=None` оставляет автоопределение. Навязывать язык нельзя: продукт
    работает с русским контентом, но фикстуры и часть роликов англоязычные, а
    неверно заданный язык даёт не ошибку, а правдоподобный бессмысленный текст.
    """
    name, compute_type = _settings()
    model = _model(name, compute_type)

    segments, _info = model.transcribe(
        str(audio),
        language=language,
        vad_filter=vad,
        word_timestamps=False,
    )

    # faster-whisper возвращает генератор: пока его не вычерпать, распознавание
    # не выполнено. Возврат генератора наружу означал бы, что ошибки прилетят
    # вызывающему в неожиданном месте, а таймкоды нельзя проверить на монотонность.
    out = [Segment(start=float(s.start), end=float(s.end), text=s.text) for s in segments]
    return out


def vad_segments(audio: str | Path) -> list[tuple[float, float]]:
    """
    Участки речи в секундах: [(начало, конец), …].

    Берётся тот же VAD (Silero), что использует transcribe с vad_filter=True —
    иначе две разметки одного файла разойдутся в границах, и таймкоды
    диаризации перестанут совпадать с таймкодами транскрипта.

    Пустой список — законный ответ: в дорожке может не быть речи вовсе. Отличать
    его от ошибки обязан вызывающий, поэтому исключения здесь не глушатся.
    """
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    sampling_rate = 16_000
    waveform = decode_audio(str(audio), sampling_rate=sampling_rate)
    chunks = get_speech_timestamps(waveform, VadOptions())
    return [
        (c["start"] / sampling_rate, c["end"] / sampling_rate)
        for c in chunks
    ]
