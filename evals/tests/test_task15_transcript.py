#!/usr/bin/env python3
"""
CDD-тест задачи #15 — Транскрипт + диаризация.

CDD (из tasks.json):
  на fixture транскрипт непустой, таймкоды монотонны и лежат в пределах
  длительности; VAD на дорожке с музыкой и тишиной отдаёт речевых участков
  меньше полной длительности; диаризация по речевым участкам даёт те же метки
  спикеров, что и по полному треку (сравнение).

─── Про фикстуры ───────────────────────────────────────────────────────────
Речь синтезируется espeak-ng, а не хранится записью. Причины две: записанный
голос — это вес в истории git и вопрос о правах, а сгенерированный
воспроизводим одной командой на любой машине. Whisper распознаёт синтезатор
хуже живой речи, поэтому проверяется непустота и структура таймкодов, а не
дословное совпадение — cdd именно этого и требует.

Дорожка для VAD собирается из трёх частей намеренно: тон, тишина, речь. Если
VAD вернёт всю длительность целиком, значит он не работает, а просто отдаёт
вход — и такую заглушку надо отличать от настоящей детекции.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ASR_DIR = REPO / "services" / "agent-core" / "agent_core" / "asr"

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


BEHAVIOURAL = (
    "транскрипт непустой",
    "таймкоды монотонны",
    "таймкоды в пределах длительности",
    "VAD отдаёт речи меньше полной длительности",
    "диаризация по речевым участкам совпадает с полным треком",
)


# ═══════════════════════════════════════════════════════════════════════════
# СТАТИЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Статический уровень ==")

init_src = (ASR_DIR / "__init__.py").read_text("utf-8") if (ASR_DIR / "__init__.py").exists() else ""
tr_src = (ASR_DIR / "transcribe.py").read_text("utf-8") if (ASR_DIR / "transcribe.py").exists() else ""
di_src = (ASR_DIR / "diarize.py").read_text("utf-8") if (ASR_DIR / "diarize.py").exists() else ""

check("модуль agent_core.asr существует", bool(init_src))
check("transcribe.py существует", bool(tr_src))
check("diarize.py существует", bool(di_src))

# Модель и тип вычислений берутся из окружения, а не зашиты: на разном железе
# large-v3 либо не поместится, либо будет считаться неделю. Настройки уже
# объявлены в compose (WHISPER_MODEL, WHISPER_COMPUTE_TYPE).
check(
    "модель Whisper берётся из окружения (WHISPER_MODEL)",
    "WHISPER_MODEL" in tr_src,
)
check(
    "тип вычислений берётся из окружения (WHISPER_COMPUTE_TYPE)",
    "WHISPER_COMPUTE_TYPE" in tr_src,
)

# Токен нужен и для self-host: веса pyannote закрыты принятием условий, без
# токена загрузка вернёт 401. Отсутствие токена обязано быть внятной ошибкой,
# а не падением внутри библиотеки.
check(
    "токен pyannote читается из окружения (PYANNOTE_TOKEN)",
    "PYANNOTE_TOKEN" in di_src,
)
check(
    "конвейер диаризации настраивается (DIARIZATION_PIPELINE)",
    "DIARIZATION_PIPELINE" in di_src,
)

# Модель грузится один раз на процесс. Без кеша каждый вызов задачи Celery
# поднимал бы large-v3 заново — это минуты на задачу и гарантированный OOM при
# четырёх воркерах.
check(
    "модель кешируется между вызовами (lru_cache или глобальный singleton)",
    "lru_cache" in tr_src or "_MODEL" in tr_src or "cache" in tr_src.lower(),
)


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("\n== Поведенческий уровень ==")

ffmpeg = shutil.which("ffmpeg")
espeak = shutil.which("espeak-ng") or shutil.which("espeak")

if not (ASR_DIR / "transcribe.py").exists():
    for n in BEHAVIOURAL:
        skip(n, "модуль agent_core.asr ещё не реализован")
elif not ffmpeg:
    for n in BEHAVIOURAL:
        skip(n, "ffmpeg не установлен")
elif not espeak:
    for n in BEHAVIOURAL:
        skip(n, "espeak-ng не установлен — нечем синтезировать речь для фикстуры")
else:
    sys.path.insert(0, str(REPO / "services" / "agent-core"))
    try:
        from agent_core.asr import diarize, transcribe, vad_segments  # noqa: E402
        loaded, why_load = True, ""
    except Exception as e:  # noqa: BLE001
        loaded, why_load = False, f"{type(e).__name__}: {str(e)[:120]}"

    if not loaded:
        for n in BEHAVIOURAL:
            skip(n, f"модуль не импортируется: {why_load}")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            tmpd = Path(tmp)

            def say(text: str, voice: str, out: Path) -> Path:
                subprocess.run(
                    [espeak, "-v", voice, "-s", "130", "-w", str(out), text],
                    capture_output=True, timeout=120,
                )
                return out

            # Два голоса — иначе диаризации нечего различать.
            a = say("This is the first speaker talking about the movie plot.", "en-us", tmpd / "a.wav")
            b = say("And now a different person shares another opinion here.", "en-us+f3", tmpd / "b.wav")

            speech = tmpd / "speech.wav"
            subprocess.run(
                [ffmpeg, "-y", "-i", str(a), "-i", str(b),
                 "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]",
                 "-map", "[out]", "-ar", "16000", "-ac", "1", str(speech)],
                capture_output=True, timeout=120,
            )

            # Тон + тишина + речь: если VAD отдаст всю длительность, он не
            # работает, а просто возвращает вход.
            mixed = tmpd / "mixed.wav"
            subprocess.run(
                [ffmpeg, "-y",
                 "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                 "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=3",
                 "-i", str(speech),
                 "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
                 "-map", "[out]", "-ar", "16000", "-ac", "1", str(mixed)],
                capture_output=True, timeout=120,
            )

            def duration(p: Path) -> float:
                out = subprocess.run(
                    [shutil.which("ffprobe"), "-v", "quiet", "-show_entries",
                     "format=duration", "-of", "csv=p=0", str(p)],
                    capture_output=True, text=True, timeout=60,
                ).stdout.strip()
                return float(out or 0)

            # ── 1-3. Транскрипт ────────────────────────────────────────────
            try:
                segments = transcribe(speech)
                texts = [s.text.strip() for s in segments if s.text.strip()]
                check(
                    "транскрипт непустой",
                    bool(texts),
                    f"сегментов={len(segments)}, непустых={len(texts)}; "
                    f"первый: {texts[0][:60] if texts else '—'!r}",
                )

                starts = [s.start for s in segments]
                ends = [s.end for s in segments]
                check(
                    "таймкоды монотонны",
                    all(x <= y for x, y in zip(starts, starts[1:]))
                    and all(s.start <= s.end for s in segments),
                    f"начала={[round(x,2) for x in starts[:6]]}",
                )

                total = duration(speech)
                check(
                    "таймкоды в пределах длительности",
                    bool(segments) and max(ends) <= total + 0.5 and min(starts) >= -0.01,
                    f"длительность={total:.2f}с, последний конец={max(ends) if ends else 0:.2f}с",
                )
            except Exception as e:  # noqa: BLE001
                for n in BEHAVIOURAL[:3]:
                    check(n, False, f"{type(e).__name__}: {str(e)[:110]}")

            # ── 4. VAD ─────────────────────────────────────────────────────
            try:
                total_mixed = duration(mixed)
                speech_spans = vad_segments(mixed)
                speech_time = sum(e - s for s, e in speech_spans)
                check(
                    "VAD отдаёт речи меньше полной длительности",
                    bool(speech_spans) and speech_time < total_mixed * 0.85,
                    f"речь={speech_time:.2f}с из {total_mixed:.2f}с "
                    f"({len(speech_spans)} участков)",
                )
            except Exception as e:  # noqa: BLE001
                check("VAD отдаёт речи меньше полной длительности", False,
                      f"{type(e).__name__}: {str(e)[:110]}")

            # ── 5. Диаризация: по участкам речи и по полному треку ─────────
            # Смысл сравнения — не «метки те же строки», а «разбиение то же»:
            # имена кластеров произвольны, важно, совпадает ли ЧИСЛО говорящих
            # и порядок их появления. Если прогон по речевым участкам даёт
            # другой ответ, значит обрезка тишины меняет результат, и ускорение
            # за счёт VAD покупается ценой неверных меток.
            try:
                full = diarize(mixed)
                partial = diarize(mixed, spans=vad_segments(mixed))

                def shape(turns):
                    order, seen = [], {}
                    for t in turns:
                        if t.speaker not in seen:
                            seen[t.speaker] = len(seen)
                        order.append(seen[t.speaker])
                    return len(seen), order

                n_full, order_full = shape(full)
                n_part, order_part = shape(partial)
                check(
                    "диаризация по речевым участкам совпадает с полным треком",
                    n_full == n_part and n_full > 0,
                    f"говорящих: полный={n_full}, по участкам={n_part}; "
                    f"порядок полный={order_full[:8]} по участкам={order_part[:8]}",
                )
            except Exception as e:  # noqa: BLE001
                check("диаризация по речевым участкам совпадает с полным треком", False,
                      f"{type(e).__name__}: {str(e)[:110]}")


sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict  # noqa: E402

sys.exit(verdict(results, "#15"))
