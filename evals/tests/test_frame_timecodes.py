#!/usr/bin/env python3
"""
Кадр, вытащенный по таймкоду, действительно с этого таймкода (п. 32).

─── Почему это проверяется прогоном, а не чтением кода ───────────────────────
В `frames/extract.py` `-ss` стоит ДО `-i`, и это сделано намеренно: так ffmpeg
перематывает по индексу, а не декодирует ролик с начала. На двухчасовом
материале разница между режимами — минуты против часов.

Плата за быструю перемотку известна: на части контейнеров и кодеков ffmpeg
встаёт на ближайший ключевой кадр РАНЬШЕ запрошенного времени. Насколько раньше
— зависит от расстояния между ключевыми кадрами, то есть от того, чем ролик
закодирован. Прочитать это по исходнику нельзя: команда одна и та же, а
поведение разное.

Цена ошибки при этом высокая и незаметная. Описание кадра уезжает в пакет с тем
таймкодом, который МЫ запросили; персона ссылается на него, судья сверяет — и
если кадр на самом деле из другого места, претензия судьи справедлива, а
виноват конвейер. Ровно такие претензии и составляли остаток отбраковок
golden-сета.

─── Как измеряется ───────────────────────────────────────────────────────────
Строится ролик, у которого КАЖДАЯ секунда своего цвета. Дальше кадры
вытаскиваются тем же кодом, что и в продакшене, и у каждого читается средний
цвет. Совпал с ожидаемым — кадр с запрошенной секунды; не совпал — видно, на
сколько секунд промахнулись и в какую сторону.

Цвет, а не наложенный текст: `drawtext` требует шрифтов и fontconfig, которых в
образе может не быть, и тест краснел бы на отсутствии шрифта, а не на дефекте.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "agent-core"))

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail and not ok else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


#: Цвета по секундам. Различаются по всем трём каналам сразу, чтобы промах на
#: одну секунду нельзя было списать на сжатие.
COLOURS = [
    ("red", (255, 0, 0)),
    ("lime", (0, 255, 0)),
    ("blue", (0, 0, 255)),
    ("yellow", (255, 255, 0)),
    ("magenta", (255, 0, 255)),
    ("cyan", (0, 255, 255)),
]

CASES = ["кадр берётся с запрошенной секунды"]

print("== Таймкоды кадров ==")

if not shutil.which("ffmpeg"):
    for c in CASES:
        skip(c, "ffmpeg недоступен — тест едет в образ воркера (CLAUDE.md §9)")
else:
    tmp = Path(tempfile.mkdtemp(prefix="agora-tc-"))
    video = tmp / "colours.mp4"

    # Ключевой кадр раз в две секунды: так у быстрой перемотки появляется
    # возможность промахнуться, и тест меряет реальное поведение, а не идеальный
    # случай «keyframe на каждом кадре».
    inputs: list[str] = []
    for name, _ in COLOURS:
        inputs += ["-f", "lavfi", "-t", "1", "-i", f"color=c={name}:s=320x240:r=25"]
    filt = "".join(f"[{i}:v]" for i in range(len(COLOURS))) + f"concat=n={len(COLOURS)}:v=1:a=0[v]"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *inputs,
         "-filter_complex", filt, "-map", "[v]",
         "-c:v", "libx264", "-g", "50", "-pix_fmt", "yuv420p", str(video)],
        capture_output=True, timeout=120, check=True,
    )

    def average_rgb(path: Path) -> tuple[int, int, int]:
        """Средний цвет кадра — сырыми байтами, без графических библиотек."""
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path),
             "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, timeout=60, check=True,
        ).stdout
        return (out[0], out[1], out[2])

    def nearest(rgb: tuple[int, int, int]) -> int:
        """Индекс ближайшего эталонного цвета."""
        return min(
            range(len(COLOURS)),
            key=lambda i: sum((a - b) ** 2 for a, b in zip(rgb, COLOURS[i][1])),
        )

    from agent_core.frames.extract import extract_frames

    # Середина секунды, а не её начало: на границе округление длительности само
    # по себе может дать соседний кадр, и это была бы претензия к арифметике, а
    # не к перемотке.
    stamps = [i + 0.5 for i in range(len(COLOURS))]
    pairs = extract_frames(video, stamps, tmp / "frames")

    wrong: list[str] = []
    for ts, path in pairs:
        expected = int(ts)
        got = nearest(average_rgb(path))
        if got != expected:
            wrong.append(f"{ts:.1f}с: кадр из секунды {got}, а не {expected}")

    check(
        CASES[0],
        not wrong and len(pairs) == len(stamps),
        f"извлечено {len(pairs)} из {len(stamps)}; промахи: {'; '.join(wrong[:4])}",
    )

print()
n_fail = sum(1 for _, s, _ in results if s == FAIL)
n_skip = sum(1 for _, s, _ in results if s == SKIP)
print(f"Итог: OK={len(results) - n_fail - n_skip} FAIL={n_fail} SKIP={n_skip}")
if n_fail:
    print("\nНевыполненные условия:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  · {name}" + (f" — {detail}" if detail else ""))
sys.exit(1 if n_fail else 0)
