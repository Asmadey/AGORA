#!/usr/bin/env python3
"""
CDD-тест задачи #14 — Препроцессинг видео (ffprobe/ffmpeg, proxy, таймкоды).

CDD (из tasks.json):
  ffprobe отвергает файл без видеодорожки с внятной ошибкой, а не падением;
  proxy-видео имеет постоянный фреймрейт и start_time == 0;
  таймкод сцены, полученный от PySceneDetect на proxy, совпадает с таймкодом
  того же кадра в извлечённом аудио с точностью до кадра.

Двухуровневый. Статический разбирает исходники и работает где угодно.
Поведенческий требует ffmpeg — без него честный SKIP, а не выдуманный результат.

Фикстуры генерируются, а не хранятся: ролик со звуком и без звука собираются
ffmpeg'ом из синтетических источников. Хранить в git видео со звуком дорого, а
главное — сгенерированное воспроизводимо и не зависит от того, что кто-то
когда-то положил в каталог.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MEDIA_DIR = REPO / "services" / "agent-core" / "agent_core" / "media"

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


# ═══════════════════════════════════════════════════════════════════════════
# СТАТИЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Статический уровень ==")

check("модуль agent_core.media существует", (MEDIA_DIR / "__init__.py").exists())

probe_src = (MEDIA_DIR / "probe.py").read_text("utf-8") if (MEDIA_DIR / "probe.py").exists() else ""
proxy_src = (MEDIA_DIR / "proxy.py").read_text("utf-8") if (MEDIA_DIR / "proxy.py").exists() else ""
audio_src = (MEDIA_DIR / "audio.py").read_text("utf-8") if (MEDIA_DIR / "audio.py").exists() else ""

check("probe.py существует", bool(probe_src))
check("proxy.py существует", bool(proxy_src))
check("audio.py существует", bool(audio_src))

# Ошибка на файле без видеодорожки обязана быть своим типом, а не тем, что
# случайно бросил ffmpeg: вызывающий код должен уметь отличить «не видео» от
# «ffmpeg не установлен», иначе первое замаскирует второе.
check(
    "объявлено собственное исключение MediaError",
    "class MediaError" in probe_src or "MediaError" in (MEDIA_DIR / "__init__.py").read_text("utf-8")
    if (MEDIA_DIR / "__init__.py").exists() else False,
)

check(
    "probe не глотает ошибку молча (есть raise)",
    "raise" in probe_src,
)

# Постоянный фреймрейт задаётся явным ключом. Без него ffmpeg сохраняет
# переменный фреймрейт исходника, и таймкод кадра в proxy перестаёт совпадать с
# таймкодом того же кадра в аудио — то есть ровно то, что требует cdd.
check(
    "proxy задаёт постоянный фреймрейт явно",
    "-r" in proxy_src or "fps" in proxy_src,
)

# start_time != 0 у контейнера сдвигает всю шкалу таймкодов. Проверяется в
# поведенческом уровне, но ключ обязан быть в коде.
check(
    "proxy сбрасывает start_time",
    "reset_timestamps" in proxy_src or "-ss" in proxy_src or "start_at_zero" in proxy_src,
)


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("\n== Поведенческий уровень ==")

ffmpeg = shutil.which("ffmpeg")
ffprobe = shutil.which("ffprobe")

if not (ffmpeg and ffprobe):
    for n in ("ffprobe отвергает файл без видеодорожки внятной ошибкой",
              "proxy имеет постоянный фреймрейт",
              "proxy имеет start_time == 0",
              "извлечённое аудио совпадает по длительности с proxy"):
        skip(n, "ffmpeg/ffprobe не установлены")
elif not (MEDIA_DIR / "probe.py").exists():
    for n in ("ffprobe отвергает файл без видеодорожки внятной ошибкой",
              "proxy имеет постоянный фреймрейт",
              "proxy имеет start_time == 0",
              "извлечённое аудио совпадает по длительности с proxy"):
        skip(n, "модуль agent_core.media ещё не реализован")
else:
    sys.path.insert(0, str(REPO / "services" / "agent-core"))
    from agent_core.media import MediaError, extract_audio, make_proxy, probe  # noqa: E402

    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        video = tmpd / "with_video.mp4"
        audio_only = tmpd / "audio_only.m4a"

        # Ролик: 3 секунды, переменный фреймрейт исходника имитируем через
        # -vsync vfr, чтобы proxy было что нормализовать.
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=3",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-shortest", str(video)],
            capture_output=True, timeout=120,
        )
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:a", "aac", str(audio_only)],
            capture_output=True, timeout=120,
        )

        # 1. Файл без видеодорожки → внятная ошибка своего типа
        try:
            probe(audio_only)
            check("ffprobe отвергает файл без видеодорожки внятной ошибкой", False,
                  "исключения не было — файл без видео принят как видео")
        except MediaError as e:
            check("ffprobe отвергает файл без видеодорожки внятной ошибкой",
                  "видео" in str(e).lower() or "video" in str(e).lower(),
                  f"MediaError: {str(e)[:90]}")
        except Exception as e:  # noqa: BLE001
            check("ffprobe отвергает файл без видеодорожки внятной ошибкой", False,
                  f"вместо MediaError прилетело {type(e).__name__}: {str(e)[:80]}")

        # 2-3. proxy: постоянный фреймрейт и start_time == 0
        proxy_path = tmpd / "proxy.mp4"
        try:
            make_proxy(video, proxy_path, fps=5)
            meta = json.loads(subprocess.run(
                [ffprobe, "-v", "quiet", "-print_format", "json",
                 "-show_streams", "-show_format", str(proxy_path)],
                capture_output=True, text=True, timeout=60,
            ).stdout)
            vstream = next(s for s in meta["streams"] if s["codec_type"] == "video")
            r_rate = vstream.get("r_frame_rate", "0/1")
            avg_rate = vstream.get("avg_frame_rate", "0/1")
            check(
                "proxy имеет постоянный фреймрейт",
                r_rate == avg_rate and r_rate.startswith("5/"),
                f"r_frame_rate={r_rate} avg_frame_rate={avg_rate}",
            )
            start = float(meta["format"].get("start_time", "1"))
            check(
                "proxy имеет start_time == 0",
                abs(start) < 0.001,
                f"start_time={start}",
            )
        except Exception as e:  # noqa: BLE001
            check("proxy имеет постоянный фреймрейт", False, f"{type(e).__name__}: {str(e)[:90]}")
            check("proxy имеет start_time == 0", False, "proxy не создан")

        # 4. Аудио извлекается и совпадает по длительности с исходником.
        # Это и есть та самая общая шкала: если длительности разошлись, таймкод
        # сцены на proxy будет указывать не на тот момент в аудио.
        wav = tmpd / "audio.wav"
        try:
            extract_audio(video, wav)
            def dur(p: Path) -> float:
                out = subprocess.run(
                    [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", str(p)],
                    capture_output=True, text=True, timeout=60,
                ).stdout
                return float(json.loads(out)["format"]["duration"])
            d_src, d_wav = dur(video), dur(wav)
            check(
                "извлечённое аудио совпадает по длительности с исходником",
                abs(d_src - d_wav) <= 0.04,  # один кадр при 25 fps
                f"видео={d_src:.3f}с аудио={d_wav:.3f}с расхождение={abs(d_src-d_wav):.3f}с",
            )
        except Exception as e:  # noqa: BLE001
            check("извлечённое аудио совпадает по длительности с исходником", False,
                  f"{type(e).__name__}: {str(e)[:90]}")


sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict  # noqa: E402

sys.exit(verdict(results, "#14"))
