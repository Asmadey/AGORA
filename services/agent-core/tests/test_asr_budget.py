"""
Расшифровка и диаризация не всегда помещаются в память одновременно.

─── Откуда цифры ─────────────────────────────────────────────────────────────
Замер на боевом сервере 18.08.2026, дорожка `15 min.mp4`, каждый прогон в
отдельном процессе, пик — `ru_maxrss`:

    pyannote speaker-diarization-community-1     2,4 ГБ    1068 с
    faster-whisper large-v3 (int8)               5,0 ГБ     352 с
    parakeet-tdt-0.6b-v3 кусками по минуте       1,2 ГБ      ~90 с

Узел `transcribe_and_diarize` запускает обе половины в потоках ОДНОГО процесса.
С whisper это 7,4 ГБ на машине, где 11,6 ГБ и живут ещё web, postgres и
LangFuse. В журнале ядра шесть убийств по OOM с anon-rss от 6,4 до 8,7 ГБ — это
они и есть.

Я успел записать эти убийства на parakeet и ошибся: parakeet до таких чисел не
доходит вовсе, он падает раньше и по другой причине (потолок 400 секунд, см.
test_parakeet_chunking). Убивало сочетание whisper + pyannote, и убивало ещё до
того, как parakeet появился в образе, — самые ранние записи от 17 августа.

─── Почему не «просто сделать последовательно» ──────────────────────────────
Параллельность здесь не украшение: по очереди эти две половины съедали 473
секунды из восьмисот, и гейт #22 не выполнялся из-за них. С parakeet сумма
пиков — 3,6 ГБ, и отказываться от параллельности незачем.

Решение принимается по замеренному расходу выбранного движка и по свободной
памяти, а не по имени модели в `if`: движков станет больше, а память на
сервере — другой.
"""

from __future__ import annotations

import sys

import pytest

from agent_core.asr import budget


def test_parakeet_and_diarization_fit_together():
    assert budget.can_run_together("parakeet-tdt-0.6b-v3", available_mb=7000), (
        "с parakeet сумма пиков 3,6 ГБ: отказ от параллельности здесь стоил бы "
        "восьми минут прогона и ничего не спасал"
    )


def test_whisper_and_diarization_do_not_fit_on_this_server():
    """7 ГБ свободных — типичное состояние сервера владельца под нагрузкой."""
    assert not budget.can_run_together("large-v3", available_mb=7000), (
        "whisper 5,0 ГБ + pyannote 2,4 ГБ = 7,4 ГБ: запуск в одном процессе "
        "убивает воркера по OOM, и выглядит это случайным сбоем прогона"
    )


def test_whisper_fits_when_the_machine_is_big_enough():
    """
    Запрет не абсолютный: на машине по §15 PRD (16 ГБ) пара помещается, и
    зашивать «whisper всегда последовательно» значило бы платить временем там,
    где платить не нужно.
    """
    assert budget.can_run_together("large-v3", available_mb=14000)


def test_unknown_engine_is_treated_as_the_hungriest():
    """
    Новый движок без замера обязан считаться самым прожорливым. Обратное
    умолчание даёт OOM в тот день, когда движок добавили, и приходит он не
    отказом, а убитым воркером.
    """
    assert not budget.can_run_together("что-то-новое", available_mb=7000)


def test_available_memory_is_read_from_the_system():
    """
    На Linux — настоящее число, иначе решение принимать не по чему. На macOS —
    ноль, и это НЕ поломка: ноль означает запрет на параллельность, то есть
    ошибку в сторону медленного прогона, а не убитого воркера. Воркер живёт в
    Linux-образе, разработка идёт на macOS, и молчаливое «наверное, хватит» на
    хосте разработчика однажды доехало бы до сервера.
    """
    value = budget.available_mb()
    if sys.platform.startswith("linux"):
        assert value > 0, (
            "на Linux /proc/meminfo прочитать не удалось: решение о "
            "параллельности станет всегда отрицательным, и прогон молча "
            "замедлится вдвое"
        )
    else:
        assert value == 0
        assert not budget.can_run_together("parakeet-tdt-0.6b-v3"), (
            "без данных о памяти обязан быть запрет, а не разрешение"
        )


@pytest.mark.parametrize("model", ["parakeet-tdt-0.6b-v3", "large-v3"])
def test_peak_is_known_for_every_offered_model(model):
    """
    Каталог настроек и таблица расхода обязаны сходиться. Модель, которую можно
    выбрать, но чей расход неизвестен, попадёт в ветку «самый прожорливый» и
    молча потеряет параллельность.
    """
    assert budget.peak_mb(model) is not None, (
        f"для {model} нет замера расхода памяти: он берётся не из документации, "
        f"а прогоном на пятнадцатиминутной дорожке"
    )


# ─── Узел обязан этим решением пользоваться ──────────────────────────────────
#
# Модуль выше можно написать, покрыть тестами и не подключить — это самый частый
# дефект в этом репозитории, и ловится он только проверкой на стыке. Поэтому
# здесь подменяются обе половины и смотрится, перекрылись они во времени или
# шли по очереди.

def _node_state(model: str) -> dict:
    return {
        "audio_ref": "/dev/null",
        "speech_regions": [],
        "settings_snapshot": {"whisperModel": model},
        "tenant_id": "t",
        "task_id": "x",
    }


class _Recorder:
    """Засекает, пересеклись ли две половины во времени."""

    def __init__(self) -> None:
        self.spans: dict[str, tuple[float, float]] = {}

    def make(self, name: str, result):
        import time

        def fn(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
            start = time.monotonic()
            time.sleep(0.05)
            self.spans[name] = (start, time.monotonic())
            return result

        return fn

    @property
    def overlapped(self) -> bool:
        a, b = self.spans["transcribe"], self.spans["diarize"]
        return a[0] < b[1] and b[0] < a[1]


@pytest.fixture
def node(monkeypatch):
    from agent_core.asr.transcribe import Segment
    from agent_core.pipeline import nodes

    rec = _Recorder()
    monkeypatch.setattr(
        nodes, "_asr", lambda state: rec.make("transcribe", [Segment(0.0, 1.0, "а")])
    )
    # Через importlib, а не `import agent_core.asr.diarize as …`: в
    # `asr/__init__.py` стоит ре-экспорт `from .diarize import diarize`, и это
    # имя перекрывает одноимённый подмодуль — обычный импорт отдаёт функцию.
    import importlib

    diarize_mod = importlib.import_module("agent_core.asr.diarize")
    monkeypatch.setattr(diarize_mod, "diarize", rec.make("diarize", []))
    return rec


def test_node_runs_in_parallel_when_memory_allows(node, monkeypatch):
    from agent_core.asr import budget as budget_mod
    from agent_core.pipeline import nodes

    monkeypatch.setattr(budget_mod, "available_mb", lambda: 14000.0)
    out = nodes.transcribe_and_diarize(_node_state("parakeet-tdt-0.6b-v3"))

    assert node.overlapped, (
        "половины пошли по очереди там, где памяти хватает: прогон стал длиннее "
        "на время диаризации без всякой причины"
    )
    assert out["transcript_raw"], "транскрипт пуст"


def test_node_runs_sequentially_when_memory_is_short(node, monkeypatch):
    from agent_core.asr import budget as budget_mod
    from agent_core.pipeline import nodes

    monkeypatch.setattr(budget_mod, "available_mb", lambda: 7000.0)
    out = nodes.transcribe_and_diarize(_node_state("large-v3"))

    assert not node.overlapped, (
        "whisper и pyannote пошли одновременно при 7 ГБ свободных: 7,4 ГБ пика "
        "убьют процесс по OOM, и прогон оборвётся без объяснения"
    )
    # Результат обязан быть тем же самым: последовательная ветка — это способ
    # исполнения, а не другое поведение.
    assert out["transcript_raw"]
    assert "stage_timings" in out
