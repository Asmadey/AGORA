"""
Whisper и pyannote читают один и тот же кэш моделей.

─── Почему проверка вообще нужна ────────────────────────────────────────────
`WhisperModel(..., download_root=X)` отдаёт X в huggingface_hub как `cache_dir`,
то есть заменяет корень кэша целиком. Когда туда передавали `HF_HOME`, веса
whisper ложились в `$HF_HOME/models--Systran--*`, а pyannote и любое другое
обращение к hub — в `$HF_HOME/hub/`. Два кэша в одном томе.

Работать это не мешало, поэтому и держалось. Цена вскрылась иначе: проверка
кэша стандартным `try_to_load_from_cache` отвечала «модели нет» при 2.9 ГБ весов
на диске, за этим последовал «ремонт» переносом каталога — и модель перестала
находиться уже по-настоящему. Расхождение, которое ничего не ломает, всё равно
стоит прохода: оно врёт диагностике.

─── Почему проверяется вызов, а не текст файла ──────────────────────────────
Сверка исходника с регулярным выражением ловит одно написание параметра и
пропускает любое другое. Здесь подменяется сам `WhisperModel`, и утверждение
формулируется о том, с чем его позвали, — это верно при любом способе записи.
"""

from __future__ import annotations

import sys
import types
from importlib import import_module

import pytest

#: Импорт через import_module, а не `from agent_core.asr import transcribe`:
#: пакет переэкспортирует функцию `transcribe`, и обычная форма отдаёт её, а не
#: модуль. Ошибка при этом приходит поздно и не по адресу — «function object has
#: no attribute _model».
MODULE = "agent_core.asr.transcribe"


@pytest.fixture
def spy(monkeypatch):
    """Подменяет faster_whisper.WhisperModel и запоминает аргументы вызова."""
    calls: list[dict] = []

    class FakeModel:
        def __init__(self, name, **kwargs):
            calls.append({"name": name, **kwargs})

    module = types.ModuleType("faster_whisper")
    module.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", module)
    return calls


def test_download_root_not_overridden(spy):
    transcribe = import_module(MODULE)

    transcribe._model.cache_clear()
    transcribe._model("large-v3", "int8")

    assert spy, "модель не создавалась — подмена не сработала"
    assert "download_root" not in spy[0], (
        "download_root заменяет корень кэша целиком, а не задаёт его родителя: "
        "веса whisper уедут из $HF_HOME/hub, где лежит всё остальное"
    )


def test_model_cache_key_covers_compute_type(spy):
    """
    Смена типа вычислений должна давать другую модель, а не выдачу из кеша.

    Настройки (#27) разрешают менять и модель, и compute_type. Если ключ кеша
    учитывает только имя, после переключения вернётся прежний объект — то есть
    настройка молча не подействует, а понять это по логам будет нельзя.
    """
    transcribe = import_module(MODULE)

    transcribe._model.cache_clear()
    transcribe._model("large-v3", "int8")
    transcribe._model("large-v3", "float32")

    assert len(spy) == 2, "compute_type не входит в ключ кеша"
    assert [c["compute_type"] for c in spy] == ["int8", "float32"]
