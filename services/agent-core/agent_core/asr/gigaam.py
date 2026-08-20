"""
Распознавание речи GigaAM (SberDevices, MIT).

─── Почему он основной ───────────────────────────────────────────────────────
Замер 20.08.2026 на пяти минутах диалога из прогона 0051, одна дорожка, один и
тот же детектор речи (`docs/ASR_BAKEOFF_2026-08-20.md`):

    parakeet-tdt-0.6b-v3   40,3 слов/мин речи | 67,0 с | 3285 МБ
    gigaam v3-e2e-rnnt     64,8 слов/мин речи | 21,2 с | 1694 МБ

Разница не в процентах: у parakeet текст не восстанавливается до смысла («Сот
мальчишек», «господин Ярат»), у GigaAM восстанавливается, и версия `e2e` даёт
пунктуацию и заглавные. На этом тексте работают три вещи сразу — ответ персоны,
проверка её ссылки судьёй и цитаты в отчёте.

─── Почему свои границы, а не его longform ───────────────────────────────────
У GigaAM есть `transcribe_longform`, и он тянет `pyannote/segmentation-3.0` из
Hugging Face — то есть заводит ВТОРОЙ детектор речи рядом с тем, что уже
работает узлом `detect_speech`. Две разметки одной дорожки разойдутся в
границах, и таймкоды транскрипта перестанут совпадать с таймкодами диаризации.

Поэтому границы берутся из нашего VAD, а нарезка — здесь.

─── Почему планировщик отдельно от модели ────────────────────────────────────
Первый замер дал покрытие речи 62 %, и виноват был не движок: участок речи
длиннее потолка модели обрезался вместо деления, и хвост не доезжал никуда.
Ровно тот же класс дефекта дал 59 % на прогоне 0051 с parakeet — «модель
молчит» там, где ошибается арифметика.

`plan_chunks` — чистая функция без весов и дорожки. Она краснеет на любой
машине, и покрытие проверяется до того, как потрачена секунда GPU.

─── Установка (см. Dockerfile воркера) ───────────────────────────────────────
Только `--no-deps`. Пакет закрепляет `onnxruntime==1.23.*`, а в образе 1.29 под
sherpa-onnx: обычная установка молча понизит его. Отдельно доставляются
`hydra-core`, `omegaconf`, `sentencepiece`, `soundfile`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from .transcribe import Segment

#: Имя модели, как его видит пользователь в Настройках.
DEFAULT_MODEL = "gigaam-v3-e2e-rnnt"

#: Соответствие имени из каталога имени внутри пакета. Отдельной таблицей, а не
#: подстрокой: имя в интерфейсе принадлежит продукту, имя в пакете — библиотеке,
#: и переименование одного не должно ломать другое.
MODEL_IDS = {
    "gigaam-v3-e2e-rnnt": "v3_e2e_rnnt",
    "gigaam-v3-rnnt": "v3_rnnt",
}

#: Сколько секунд модель принимает за раз.
#:
#: Энкодер GigaAM обучен на отрезках до 30 секунд; на более длинных качество
#: падает, а не растёт. Двадцать пять — с запасом на то, что граница куска
#: ставится по тишине и может уехать на долю секунды.
CHUNK_LIMIT_SEC = 25.0

#: Пауза, через которую куски не сливаются.
#:
#: Слить два участка через минуту тишины значит отправить эту минуту в модель:
#: это и оплаченное время, и приглашение галлюцинировать на пустом месте.
#: Секунда — типичная пауза между репликами внутри сцены; всё, что длиннее,
#: разрывает кусок.
MAX_GAP_SEC = 1.0

Span = tuple[float, float]


def plan_chunks(
    speech: list[Span],
    *,
    limit: float = CHUNK_LIMIT_SEC,
    max_gap: float = MAX_GAP_SEC,
) -> list[Span]:
    """
    Куски, которые целиком покрывают речь и не длиннее потолка.

    Три свойства, за каждое отвечает свой тест:

    * **полнота** — объединение кусков покрывает каждый участок речи целиком;
      участок длиннее потолка ДЕЛИТСЯ, а не обрезается;
    * **потолок** — ни один кусок не длиннее `limit`;
    * **экономность** — соседние участки сливаются, пока помещаются и пока
      пауза между ними короче `max_gap`.

    Куски идут по возрастанию и не накладываются: наложение дало бы одну реплику
    дважды с разным временем, и ссылку персоны на момент стало бы нечем
    проверить.
    """
    out: list[Span] = []
    for start, end in sorted(speech):
        if end <= start:
            continue

        # Длинный участок делится на последовательные части. Именно здесь
        # терялся хвост: `min(end, start + limit)` отбрасывал остаток.
        while end - start > limit:
            out.append((start, start + limit))
            start += limit

        if out:
            prev_start, prev_end = out[-1]
            fits = end - prev_start <= limit
            close = start - prev_end <= max_gap
            if fits and close:
                out[-1] = (prev_start, end)
                continue

        out.append((start, end))
    return out


@lru_cache(maxsize=1)
def _model(model_id: str):
    """
    Загруженная модель. Кеш обязателен, а не оптимизация: без него каждая задача
    Celery поднимала бы веса заново — это минуты на задачу и по копии модели на
    процесс prefork.

    Импорт внутри функции: `gigaam` тянет torch, и платить за него там, где
    распознавание не нужно (статический уровень тестов), незачем.
    """
    import gigaam

    return gigaam.load_model(
        model_id,
        device="cpu",
        download_root=os.environ.get("GIGAAM_HOME") or None,
    )


def transcribe(audio: str | Path, model: str | None = None, **_: object) -> list[Segment]:
    """
    Речь в текст с таймкодами от начала дорожки.

    Сигнатура повторяет `asr.transcribe.transcribe`: конвейер зовёт движки через
    одну обёртку и не должен знать, какой из них выбран.

    Кусок, на котором модель промолчала, в результат не попадает. Это не
    косметика: пустая реплика с таймкодами выглядела бы как распознанная тишина
    и завышала бы покрытие речи — метрику, по которой мы этот движок и меняем.
    """
    import soundfile as sf

    from .transcribe import vad_segments

    path = str(audio)
    model_id = MODEL_IDS.get(model or DEFAULT_MODEL, MODEL_IDS[DEFAULT_MODEL])
    chunks = plan_chunks(vad_segments(path))
    if not chunks:
        return []

    data, rate = sf.read(path, dtype="float32")
    if getattr(data, "ndim", 1) > 1:  # стерео → моно, модель ждёт одну дорожку
        data = data.mean(axis=1)

    engine = _model(model_id)
    out: list[Segment] = []
    for start, end in chunks:
        piece = data[int(start * rate):int(end * rate)]
        text = str(engine.transcribe_sample(piece) if hasattr(engine, "transcribe_sample")
                   else _via_file(engine, piece, rate)).strip()
        if text:
            out.append(Segment(start=start, end=end, text=text))
    return out


def _via_file(engine, piece, rate: int) -> str:
    """
    Запасной путь: у части версий пакета публичный вход только по файлу.

    Временный файл на кусок дешевле, чем разбираться в приватном API: двадцать
    пять секунд моно 16 кГц — это восемьсот килобайт.
    """
    import tempfile

    import soundfile as sf

    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        sf.write(tmp.name, piece, rate)
        return engine.transcribe(tmp.name)
