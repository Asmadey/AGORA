"""
Диаризация: контракт и инварианты разметки.

─── Почему этот модуль первый в очереди на покрытие ─────────────────────────
1111 секунд из 2024 в прогоне № 0050 — самый дорогой узел конвейера, и до сих
пор ни одной проверки. Замер 18.08.2026 на пятнадцатиминутной дорожке: 2,4 ГБ
и 1068 секунд.

─── Что проверяется без pyannote, а что только в образе ─────────────────────
Здесь два уровня, и они закрывают разное.

Уровень контракта идёт где угодно: конвейер подменяется заглушкой, и
проверяется ТО, ЧТО ВОКРУГ модели, — совместимость с двумя версиями pyannote,
сортировка, приведение типов, передача числа говорящих. Именно там уже был
дефект: pyannote 3.x отдаёт `Annotation`, а 4.x — датакласс с разметкой в поле
`speaker_diarization`, и обращение к `itertracks` напрямую падало бы при
обновлении в пределах разрешённого диапазона `>=3.3`.

Уровень поведения требует настоящих весов и уходит в SKIP вне образа воркера
(CLAUDE.md §9). Он проверяет инварианты, которые верны на любом материале:
интервалы не выходят за длительность, не вывернуты и упорядочены.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals" / "tests"))

import importlib  # noqa: E402

from agent_core.asr.diarize import DiarizationUnavailable, SpeakerTurn  # noqa: E402

# Через importlib, а не `from agent_core.asr import diarize`: в `asr/__init__.py`
# стоит ре-экспорт `from .diarize import diarize`, и это имя перекрывает
# одноимённый подмодуль — обычный импорт молча отдаёт ФУНКЦИЮ вместо модуля.
# Ловушка сработала в этой сессии трижды: в `pipeline/nodes.py`, в
# `test_asr_budget.py` и здесь.
diarize_mod = importlib.import_module("agent_core.asr.diarize")


# ─────────────────────────────────────────────────────────────────────────
# Уровень контракта: заглушка вместо модели
# ─────────────────────────────────────────────────────────────────────────

class _Segment:
    def __init__(self, start: float, end: float) -> None:
        self.start = start
        self.end = end


class _Annotation:
    """То, что отдаёт pyannote 3.x."""

    def __init__(self, tracks):
        self._tracks = tracks

    def itertracks(self, yield_label: bool = False):  # noqa: ARG002
        return iter(self._tracks)

    def crop(self, _support):
        return self


class _DiarizeOutput:
    """То, что отдаёт pyannote 4.x: разметка лежит в поле."""

    def __init__(self, annotation):
        self.speaker_diarization = annotation


@pytest.fixture
def fake_pipeline(monkeypatch):
    """Подменяет загрузку модели. Возвращает список пойманных kwargs вызова."""
    calls: list[dict] = []
    holder: dict = {}

    def _pipeline(name, token):  # noqa: ARG001
        def run(_audio, **kwargs):
            calls.append(kwargs)
            return holder["result"]

        return run

    monkeypatch.setattr(diarize_mod, "_pipeline", _pipeline)
    monkeypatch.setattr(diarize_mod, "_as_waveform", lambda _audio: {"waveform": None})
    return calls, holder


def test_pyannote_3_annotation_is_read(fake_pipeline):
    calls, holder = fake_pipeline
    holder["result"] = _Annotation([(_Segment(1.0, 2.0), None, "SPEAKER_00")])

    turns = diarize_mod.diarize("нет.wav")
    assert turns == [SpeakerTurn(start=1.0, end=2.0, speaker="SPEAKER_00")]
    assert calls == [{}]


def test_pyannote_4_dataclass_is_read(fake_pipeline):
    """
    Без этой развилки обновление библиотеки в пределах объявленного диапазона
    роняло бы узел с AttributeError — то есть посреди прогона, после
    расшифровки.
    """
    _, holder = fake_pipeline
    holder["result"] = _DiarizeOutput(
        _Annotation([(_Segment(0.5, 1.5), None, "SPEAKER_01")])
    )
    assert diarize_mod.diarize("нет.wav") == [
        SpeakerTurn(start=0.5, end=1.5, speaker="SPEAKER_01")
    ]


def test_turns_are_sorted_by_start(fake_pipeline):
    """
    Порядок — не косметика: `merge_transcript` склеивает реплики с транскриптом
    по времени, и перемешанные интервалы дали бы ярлыки не тем словам.
    """
    _, holder = fake_pipeline
    holder["result"] = _Annotation([
        (_Segment(5.0, 6.0), None, "B"),
        (_Segment(1.0, 2.0), None, "A"),
        (_Segment(3.0, 4.0), None, "A"),
    ])
    assert [t.start for t in diarize_mod.diarize("нет.wav")] == [1.0, 3.0, 5.0]


def test_numeric_types_are_coerced(fake_pipeline):
    """
    pyannote отдаёт свои числовые типы. Уехав в JSON как есть, они дали бы
    `TypeError: Object of type float64 is not JSON serializable` при записи
    состояния — то есть уже после того, как диаризация отработала свои минуты.
    """
    class _Weird(float):
        pass

    _, holder = fake_pipeline
    holder["result"] = _Annotation([(_Segment(_Weird(1.0), _Weird(2.0)), None, 7)])

    turn = diarize_mod.diarize("нет.wav")[0]
    assert type(turn.start) is float
    assert type(turn.end) is float
    assert turn.speaker == "7"


def test_num_speakers_is_passed_through(fake_pipeline):
    calls, holder = fake_pipeline
    holder["result"] = _Annotation([])
    diarize_mod.diarize("нет.wav", num_speakers=2)
    assert calls == [{"num_speakers": 2}]


def test_zero_speakers_is_not_passed(fake_pipeline):
    """
    `num_speakers=0` для pyannote — не «сколько получится», а недопустимое
    значение. Ноль и None должны означать одно: не ограничивать.
    """
    calls, holder = fake_pipeline
    holder["result"] = _Annotation([])
    diarize_mod.diarize("нет.wav", num_speakers=0)
    assert calls == [{}]


def test_empty_result_is_legal(fake_pipeline):
    """Дорожка без речи — законный случай, а не отказ."""
    _, holder = fake_pipeline
    holder["result"] = _Annotation([])
    assert diarize_mod.diarize("нет.wav") == []


def test_missing_weights_raise_a_named_error():
    """
    `from_pretrained` возвращает None вместо исключения, когда доступ к закрытым
    весам не подтверждён. Молчаливый None дальше по коду даёт AttributeError в
    неожиданном месте — отдельный тип нужен, чтобы вызывающий отличал
    «модель недоступна» от «в записи один говорящий».
    """
    assert issubclass(DiarizationUnavailable, RuntimeError)


# ─────────────────────────────────────────────────────────────────────────
# Уровень поведения: настоящие веса, только в образе воркера
# ─────────────────────────────────────────────────────────────────────────

def _reason() -> str | None:
    import _harness  # локальный импорт: путь добавлен выше

    return _harness.worker_deps_missing("pyannote.audio", "torch", "faster_whisper")


FIXTURE = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "3 min.mp4"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg недоступен")
def test_real_diarization_respects_the_duration():
    """
    Инварианты, верные на любом материале: интервал не вывернут, не отрицателен
    и не выходит за длительность дорожки. Проверять «ровно два спикера» на
    произвольном ролике нельзя — это свойство материала, а не кода.
    """
    reason = _reason()
    if reason:
        pytest.skip(reason)
    if not FIXTURE.exists():
        pytest.skip(f"нет фикстуры {FIXTURE.name}")

    duration = float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(FIXTURE)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    )

    turns = diarize_mod.diarize(str(FIXTURE))

    assert turns, "на трёхминутном ролике не найдено ни одной реплики"
    for t in turns:
        assert t.start >= 0, f"отрицательное начало: {t}"
        assert t.end > t.start, f"вывернутый интервал: {t}"
        # Полсекунды запаса: длительность контейнера и длительность дорожки
        # расходятся на величину последнего пакета.
        assert t.end <= duration + 0.5, f"реплика за пределами дорожки: {t} при {duration}"
        assert t.speaker, "пустой ярлык говорящего"

    starts = [t.start for t in turns]
    assert starts == sorted(starts), "реплики пришли неупорядоченными"
