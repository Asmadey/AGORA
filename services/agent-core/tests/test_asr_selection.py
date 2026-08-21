"""
Модель распознавания берётся из снимка настроек прогона, а не из окружения.

─── Как это нашлось ──────────────────────────────────────────────────────────
Владелец выбрал в Настройках `large-v3-turbo`, сохранил, запустил прогон № 0050
— и получил текст от `large-v3`. Разбор данных прогона:

    settings_snapshot.whisperModel = "large-v3-turbo"
    кэш воркера                    = models--Systran--faster-whisper-large-v3

Turbo не скачивался, потому что его никто не спрашивал: `asr/transcribe.py`
читал модель из `os.environ["WHISPER_MODEL"]`, а снимок задачи в эту функцию
никогда не передавался. `TranscriptionConfig.for_task()` при этом написан,
задокументирован и покрыт тестом — и не вызывался из пути транскрипции.

Тот же класс, что и остальные находки этой сессии: механизм построен, проверен и
не подключён. Заметить его было неоткуда — выбор сохраняется, прогон идёт, текст
появляется. Отличается только модель, а сравнить не с чем.

─── Почему проверяется вызовом, а не чтением исходника ───────────────────────
Исходник и сейчас выглядит правильным: в конфигурации есть `for_task`, в
настройках есть поле, в снимке есть значение. Разрыв ровно в одном месте — между
ними, — и увидеть его можно только исполнением.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from agent_core.asr.transcribe import Segment
from agent_core.pipeline import nodes


class Recorder:
    """Подставной распознаватель: запоминает, с какой моделью его позвали."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, audio: Any, *, model: str | None = None, **kw: Any) -> list[Segment]:
        self.calls.append({"audio": str(audio), "model": model, **kw})
        return [Segment(start=0.0, end=1.0, text="раз")]


@pytest.fixture
def engines(monkeypatch: pytest.MonkeyPatch) -> dict[str, Recorder]:
    out = {"whisper": Recorder(), "parakeet": Recorder()}
    monkeypatch.setattr(
        importlib.import_module("agent_core.asr.transcribe"), "transcribe", out["whisper"],
    )
    monkeypatch.setattr(
        importlib.import_module("agent_core.asr.parakeet"), "transcribe", out["parakeet"],
    )
    return out


def _state(model: str | None) -> dict[str, Any]:
    snapshot = {"whisperModel": model} if model is not None else {}
    return {"audio_ref": "/tmp/a.wav", "settings_snapshot": snapshot}


def test_snapshot_model_reaches_the_engine(engines, monkeypatch):
    """
    Выбранная модель доезжает до вызова.

    Именно этого не было: движок выбирался по снимку, а сама модель бралась из
    окружения — то есть выбор между двумя моделями одного движка не значил
    ничего.
    """
    monkeypatch.setenv("WHISPER_MODEL", "large-v3")

    nodes.transcribe(_state("large-v3"))

    assert engines["whisper"].calls, "должен был позваться whisper"
    assert engines["whisper"].calls[0]["model"] == "large-v3"
    assert not engines["parakeet"].calls


def test_snapshot_switches_the_engine_too(engines, monkeypatch):
    """Смена модели меняет и движок, не только имя."""
    monkeypatch.setenv("WHISPER_MODEL", "large-v3")

    nodes.transcribe(_state("parakeet-tdt-0.6b-v3"))

    assert engines["parakeet"].calls, "должен был позваться parakeet"
    assert engines["parakeet"].calls[0]["model"] == "parakeet-tdt-0.6b-v3"
    assert not engines["whisper"].calls


def test_env_is_the_fallback_for_old_tasks(engines, monkeypatch):
    """
    Пустой снимок — откат на окружение.

    Задачи, поставленные до появления настроек, обязаны остаться исполнимыми:
    падение на них означало бы, что старый прогон нельзя перезапустить.
    """
    monkeypatch.setenv("WHISPER_MODEL", "large-v3")

    nodes.transcribe(_state(None))

    assert engines["whisper"].calls[0]["model"] == "large-v3"
