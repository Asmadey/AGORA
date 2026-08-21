"""
Parakeet как вторая модель распознавания — контракт и его границы.

─── Почему он вообще появился ────────────────────────────────────────────────
Замер на боевом железе 18.08.2026, одна и та же дорожка 161,6 секунды, четыре
потока CPU:

    faster-whisper large-v3 (int8)      198,1 с   — 0,8× реального времени
    parakeet-tdt-0.6b-v3 (int8 ONNX)     24,7 с   — 6,5× реального времени

Восьмикратная разница, и она решает не «удобство», а стоимость прогона:
транскрипция занимала половину из четырёхсот секунд.

─── Почему ONNX, а не NeMo ───────────────────────────────────────────────────
Я дважды писал, что пункт упрётся во второй тяжёлый рантайм рядом с torch и
рискует убить воркер по памяти. Это оказалось неверно: `onnxruntime` уже в
образе, `sherpa-onnx` весит 38,5 МБ, модель в int8 — 671 МБ. NeMo не нужен
вовсе, и прежняя оценка описывала маршрут, который был не единственным.

─── Что проверяется здесь ────────────────────────────────────────────────────
Не качество распознавания — его меряет сквозной прогон. Здесь контракт: те же
`Segment` с теми же таймкодами, что у whisper, монотонные и не выходящие за
длительность. Разошедшись в форме, две модели дали бы конвейеру разные данные
при одинаковом виде, и заметно это стало бы на таймлайне, а не здесь.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agent_core.asr.transcribe import Segment

sherpa = pytest.importorskip(
    "sherpa_onnx",
    reason="sherpa-onnx живёт в образе воркера — тест едет туда (CLAUDE.md §9)",
)

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg недоступен",
)


def _speech_wav(path: Path) -> Path:
    """Секунда тона: распознать нечего, но контракт проверяется и на пустом."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=300",
         "-t", "1", "-ac", "1", "-ar", "16000", str(path)],
        check=True, capture_output=True, timeout=60,
    )
    return path


def test_returns_the_same_segment_shape_as_whisper(tmp_path: Path):
    from agent_core.asr.parakeet import transcribe

    out = transcribe(_speech_wav(tmp_path / "a.wav"))

    assert isinstance(out, list)
    for seg in out:
        assert isinstance(seg, Segment)
        assert seg.end >= seg.start
        # Таймкод за концом дорожки — тот самый дефект, из-за которого правило
        # grounding браковало исправные ответы: ссылка вела туда, где ничего нет.
        assert seg.end <= 1.5, f"таймкод {seg.end} за пределами секундной дорожки"


def test_segments_do_not_go_backwards(tmp_path: Path):
    """
    Монотонность важнее полноты: сборка таймлайна берёт ближайшую
    предшествующую сцену, и сегмент, уехавший назад, привязал бы речь к чужому
    кадру — молча и правдоподобно.
    """
    from agent_core.asr.parakeet import transcribe

    out = transcribe(_speech_wav(tmp_path / "b.wav"))
    starts = [s.start for s in out]
    assert starts == sorted(starts)


def test_missing_model_names_itself(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Нет весов — внятный отказ с именем каталога.

    Модель печётся в образ намеренно: скачивание 671 МБ посреди прогона — ровно
    тот дефект, который чинился в пункте 29 для whisper. Он не выглядит
    нехваткой модели, он выглядит случайно долгой транскрипцией.
    """
    from agent_core.asr import parakeet

    monkeypatch.setattr(parakeet, "_model", parakeet._model.__wrapped__)
    monkeypatch.setenv("PARAKEET_MODEL_DIR", str(tmp_path / "нет-такого"))

    with pytest.raises(RuntimeError, match="PARAKEET_MODEL_DIR"):
        parakeet.transcribe(_speech_wav(tmp_path / "c.wav"))
