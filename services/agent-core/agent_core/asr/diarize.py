"""
Диаризация — кто говорит и когда (задача #15).

pyannote.audio, локально. Веса закрыты принятием условий на Hugging Face, поэтому
нужен токен даже при self-host: без него загрузка возвращает 401, и выглядит это
как сетевая ошибка, а не как отсутствие доступа.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_PIPELINE = "pyannote/speaker-diarization-community-1"


class DiarizationUnavailable(RuntimeError):
    """
    Диаризацию выполнить нечем: нет токена или не скачались веса.

    Отдельный тип, чтобы вызывающий отличал «модель недоступна» от «в записи
    один говорящий». Второе — законный результат, первое — поломка настройки, и
    сваливать их в одно исключение значит однажды принять сломанную диаризацию
    за моноспикерную запись.
    """


@dataclass(frozen=True)
class SpeakerTurn:
    """Реплика: интервал и метка говорящего."""

    start: float
    end: float
    speaker: str


@lru_cache(maxsize=1)
def _pipeline(name: str, token: str):
    """
    Загруженный конвейер. Кеш по той же причине, что у Whisper: без него каждая
    задача Celery тянула бы веса заново.
    """
    try:
        from pyannote.audio import Pipeline
    except ImportError as e:  # noqa: BLE001
        raise DiarizationUnavailable(
            "pyannote.audio не установлен — проверьте сборку образа воркера"
        ) from e

    # Имя параметра для токена менялось: в pyannote.audio 3.x это
    # use_auth_token, в 4.x — token, и старое имя убрано, а не помечено
    # устаревшим. Пробуем новое, откатываемся на старое: закреплять одно значит
    # ломаться при обновлении библиотеки в сторону, которую сами же и разрешили
    # диапазоном >=3.3 в pyproject.
    try:
        pipeline = Pipeline.from_pretrained(name, token=token or None)
    except TypeError:
        pipeline = Pipeline.from_pretrained(name, use_auth_token=token or None)

    if pipeline is None:
        # from_pretrained возвращает None вместо исключения, когда доступ к
        # закрытым весам не подтверждён. Молчаливый None дальше по коду даёт
        # AttributeError в неожиданном месте — превращаем его в внятный отказ здесь.
        raise DiarizationUnavailable(
            f"не удалось загрузить {name}: веса закрыты принятием условий на "
            f"Hugging Face. Проверьте PYANNOTE_TOKEN и что условия приняты в "
            f"профиле модели."
        )
    return pipeline


def diarize(
    audio: str | Path,
    spans: list[tuple[float, float]] | None = None,
    num_speakers: int | None = None,
) -> list[SpeakerTurn]:
    """
    Размечает дорожку по говорящим.

    `spans` — участки речи от VAD. Передавать их не обязательно, но полезно:
    диаризация по тишине тратит время и добавляет ложные кластеры из шума.
    Пункт cdd требует, чтобы результат при этом не менялся — то есть ускорение
    не должно покупаться ценой других меток.

    Ограничение области реализовано через `Timeline`, а не обрезкой файла:
    обрезка сдвинула бы таймкоды, и их пришлось бы пересчитывать обратно —
    место, где ошибка на полсекунды никем не замечается.
    """
    name = os.environ.get("DIARIZATION_PIPELINE", DEFAULT_PIPELINE)
    token = os.environ.get("PYANNOTE_TOKEN", "")
    pipeline = _pipeline(name, token)

    kwargs: dict = {}
    if num_speakers:
        kwargs["num_speakers"] = num_speakers

    raw = pipeline(str(audio), **kwargs)

    # pyannote 3.x возвращает Annotation напрямую; 4.x — датакласс DiarizeOutput,
    # где разметка лежит в поле speaker_diarization (рядом с ней — вариант без
    # перекрывающейся речи и эмбеддинги). Обращаться к itertracks у датакласса
    # значит падать с AttributeError при обновлении библиотеки в пределах
    # разрешённого диапазона >=3.3.
    annotation = getattr(raw, "speaker_diarization", raw)

    if spans:
        from pyannote.core import Segment as PSegment
        from pyannote.core import Timeline

        # Область ограничивается после разметки, а не обрезкой файла до неё:
        # обрезка сдвинула бы таймкоды, и их пришлось бы пересчитывать обратно —
        # место, где ошибка на полсекунды никем не замечается.
        timeline = Timeline([PSegment(start, end) for start, end in spans])
        annotation = annotation.crop(timeline.support())

    turns = [
        SpeakerTurn(start=float(segment.start), end=float(segment.end), speaker=str(label))
        for segment, _track, label in annotation.itertracks(yield_label=True)
    ]
    turns.sort(key=lambda t: t.start)
    return turns
