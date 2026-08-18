"""
Расшифровка и диаризация идут одновременно, а не одна за другой.

─── Что показал замер ───────────────────────────────────────────────────────
Тайминги узлов (их добавил этап В) на сквозном прогоне трёхминутного ролика:

    transcribe        245 с
    diarize           228 с
    analyze_chunks     58 с
    evaluate_personas 300 с

Гейт #22 требует уложить короткий режим в 600 с; прогон шёл 620–980. Причина не
в разборе кадров — он стоит 58 секунд из восьмисот с лишним, — а в том, что
расшифровка и диаризация идут ПОСЛЕДОВАТЕЛЬНО и вместе съедают 473 секунды.

PRD §8 объявляет их параллельными («WhisperX ∥ pyannote»), и граф это отражает:
`detect_speech` ветвится на два узла, оба сходятся в `merge_transcript`.
Параллелизм там оказался структурным, а не временным — разные каналы состояния,
чтобы LangGraph не отверг одновременную запись, — но исполняются ветки по
очереди: Pregel в синхронном режиме проходит суперступень узел за узлом.

─── Почему не ainvoke ───────────────────────────────────────────────────────
Асинхронный запуск графа заставил бы LangGraph развести ветки по потокам сам. Но
чекпоинтер прогона (`ValkeyCheckpointSaver`) реализует только синхронные `put` и
`get_tuple`; переводить на асинхронный запуск пришлось бы и его, а он — то
единственное, что позволяет прогону пережить перезапуск воркера посреди
пятнадцатиминутной транскрипции.

Поэтому оба вызова живут в одном узле и разводятся по потокам явно. И whisper
(CTranslate2), и pyannote (torch) отпускают GIL на время счёта, поэтому потоки
дают настоящее перекрытие, а не видимость. На восьми ядрах при OMP_NUM_THREADS=4
каждый занимает половину — вместе они занимают машину целиком.

─── Что здесь проверяется ───────────────────────────────────────────────────
Не «стало быстрее» — это свойство железа и замеряется прогоном. Проверяется то,
что зависит от кода: обе работы действительно перекрываются во времени, отказ
диаризации по-прежнему не роняет прогон, и длительность каждой половины
по-прежнему видна по отдельности.
"""

from __future__ import annotations

import time

from agent_core.pipeline import nodes


class _Slow:
    """Работа, которая честно спит, отпуская GIL, — как это делают whisper и torch."""

    def __init__(self, seconds: float, result: object):
        self.seconds = seconds
        self.result = result
        self.started_at: float | None = None
        self.finished_at: float | None = None

    def __call__(self, *args: object, **kwargs: object) -> object:
        self.started_at = time.monotonic()
        time.sleep(self.seconds)
        self.finished_at = time.monotonic()
        return self.result


class _Segment:
    def __init__(self, start: float, end: float, text: str):
        self.start, self.end, self.text = start, end, text


class _Turn:
    def __init__(self, start: float, end: float, speaker: str):
        self.start, self.end, self.speaker = start, end, speaker


STATE = {"audio_ref": "/tmp/audio.wav", "speech_regions": [[0.0, 5.0]]}


def _patch(monkeypatch, transcribe_work, diarize_work):
    """
    Подменяет обе тяжёлые библиотеки на управляемые заглушки.

    Модули берутся через `importlib.import_module`, а не через
    `import agent_core.asr.transcribe as m` — и это не педантизм.
    `agent_core/asr/__init__.py` реэкспортирует функцию `transcribe`, и в
    пространстве имён пакета она ЗАТЕНЯЕТ одноимённый
    подмодуль: такой импорт возвращает функцию, а не модуль, и подмена ложится на
    объект функции, ничего не меняя. Узел при этом продолжает звать настоящую
    библиотеку — и падает `ModuleNotFoundError: faster_whisper` там, где тест
    рассчитывал на заглушку.
    """
    import importlib

    # Заглушка ставится ОБОИМ движкам: с версии, где parakeet стал моделью по
    # умолчанию, конвейер выбирает распознаватель по снимку настроек, и стаб
    # только на whisper перестал перехватывать вызов — тест уходил в настоящий
    # ONNX и падал на отсутствии весов. Проверяется здесь параллельность, а не
    # то, какая модель считает, поэтому глушим обе.
    for module in ("agent_core.asr.transcribe", "agent_core.asr.parakeet"):
        monkeypatch.setattr(
            importlib.import_module(module), "transcribe", transcribe_work,
        )
    monkeypatch.setattr(
        importlib.import_module("agent_core.asr.diarize"),
        "diarize", diarize_work,
    )
    # Свободная память задаётся явно. С 18.08.2026 узел решает по ней, идти в
    # два потока или по очереди (см. agent_core/asr/budget.py), и без этой
    # строки тест мерил бы не код, а объём памяти машины, на которой он идёт, —
    # на macOS `available_mb()` честно отдаёт ноль, и параллельности не будет.
    monkeypatch.setattr(
        importlib.import_module("agent_core.asr.budget"),
        "available_mb", lambda: 14000.0,
    )


def test_both_halves_overlap_in_time(monkeypatch):
    """
    Вторая работа начинается ДО того, как кончилась первая.

    Проверяется перекрытие, а не суммарное время: время зависит от машины, а
    перекрытие — от кода. Последовательный порядок дал бы started_at второй
    работы позже, чем finished_at первой.
    """
    slow_transcribe = _Slow(0.4, [_Segment(0.0, 1.0, "речь")])
    slow_diarize = _Slow(0.4, [_Turn(0.0, 1.0, "SPEAKER_00")])
    _patch(monkeypatch, slow_transcribe, slow_diarize)

    started = time.monotonic()
    update = nodes.transcribe_and_diarize(STATE)  # type: ignore[arg-type]
    elapsed = time.monotonic() - started

    assert slow_transcribe.started_at is not None
    assert slow_diarize.started_at is not None
    # Каждая началась раньше, чем кончилась другая — то есть они пересеклись.
    assert slow_diarize.started_at < slow_transcribe.finished_at
    assert slow_transcribe.started_at < slow_diarize.finished_at
    # И вместе заняли заметно меньше суммы. Порог щедрый: тест мерит код, а не
    # загруженность машины, на которой он идёт.
    assert elapsed < 0.7, f"обе половины заняли {elapsed:.2f} с вместо ~0.4"

    assert update["transcript_raw"] == [{"start": 0.0, "end": 1.0, "text": "речь"}]
    assert update["speaker_turns"] == [
        {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"}
    ]


def test_diarization_failure_still_degrades_instead_of_failing(monkeypatch):
    """
    Недоступность pyannote — не отказ прогона.

    Свойство было у отдельного узла, и слияние узлов не повод его потерять:
    транскрипт без ярлыков спикеров остаётся полезным, а исследование про
    реакцию зрителя, а не про то, кто говорит.
    """
    from agent_core.asr.diarize import DiarizationUnavailable

    def failing(*args: object, **kwargs: object) -> object:
        raise DiarizationUnavailable("нет токена")

    _patch(monkeypatch, _Slow(0.05, [_Segment(0.0, 1.0, "речь")]), failing)

    update = nodes.transcribe_and_diarize(STATE)  # type: ignore[arg-type]

    assert update["speaker_turns"] == []
    assert any("diarize" in d for d in update["degraded"])
    # Расшифровка при этом на месте: одна половина не тянет за собой другую.
    assert update["transcript_raw"]


def test_transcription_failure_is_a_failure(monkeypatch):
    """
    Отказ расшифровки роняет прогон, и это правильно.

    Без транскрипта персонам показывать нечего: разбор кадров описывает
    картинку, а содержание речи берётся только отсюда. Деградация здесь дала бы
    отчёт по немому ролику, выглядящий полноценным.
    """
    def failing(*args: object, **kwargs: object) -> object:
        raise RuntimeError("whisper не поднялся")

    _patch(monkeypatch, failing, _Slow(0.05, []))

    try:
        nodes.transcribe_and_diarize(STATE)  # type: ignore[arg-type]
    except RuntimeError as exc:
        assert "whisper" in str(exc)
    else:
        raise AssertionError("отказ расшифровки обязан дойти до вызывающего")


def test_each_half_reports_its_own_duration(monkeypatch):
    """
    Длительность каждой половины видна по отдельности.

    Ровно эта разбивка и показала, куда уходит время. Слив два узла в один, мы
    потеряли бы её на уровне графа — значит узел обязан отдать её сам.
    """
    _patch(monkeypatch, _Slow(0.2, []), _Slow(0.05, []))

    update = nodes.transcribe_and_diarize(STATE)  # type: ignore[arg-type]
    stages = update["stage_timings"]

    assert stages["transcribe"] >= 0.2
    assert stages["diarize"] >= 0.05
    assert stages["transcribe"] > stages["diarize"]
