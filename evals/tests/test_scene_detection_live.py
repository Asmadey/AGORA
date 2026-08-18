#!/usr/bin/env python3
"""
Детекция сцен на настоящем ролике: склейки находятся там, где они есть (п. 24).

─── Что здесь проверяется ────────────────────────────────────────────────────
`build_scenes` — сборка сцен из готового списка склеек — покрыта модульными
тестами: там арифметика границ, и она проверяется без видео. А вот сам поиск
склеек — `_detect_cuts` через PySceneDetect — не проверялся ничем: о нём было
известно только то, что порог равен 27 и что шкала у него 0…255 по HSV.

Порог, выбранный вслепую, ошибается в обе стороны и обе ошибки тихие. Слишком
низкий объявляет склейкой смену освещения, и ролик рассыпается на десятки
«сцен», каждая со своим описанием и таймкодом. Слишком высокий склеивает разные
планы в один, и персона получает описание, относящееся к другому моменту.

Поэтому здесь строится ролик с ЗАВЕДОМО известными склейками, и проверяется, что
найдены ровно они. Не «детектор что-то нашёл», а «нашёл там, где есть».

─── Про неразрезанный ролик ──────────────────────────────────────────────────
Второй случай — непрерывная съёмка без единой склейки: интервью, запись экрана,
монолог на камеру. Список сцен и тогда не бывает пустым, а длинный отрезок
режется на равные блоки. Проверяется и это: ролик без монтажа — не исключение, а
самый частый вид материала в продукте.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "agent-core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness  # noqa: E402

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail and not ok else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


CASES = [
    "склейки найдены там, где они есть",
    "ролик без монтажа режется на блоки, а не остаётся одной сценой",
]

print("== Детекция сцен на настоящем ролике ==")

missing = _harness.worker_deps_missing("scenedetect")
if not shutil.which("ffmpeg"):
    for c in CASES:
        skip(c, "ffmpeg недоступен — тест едет в образ воркера (CLAUDE.md §9)")
elif missing:
    for c in CASES:
        skip(c, missing)
else:
    from agent_core.frames.scenes import MAX_SCENE_SEC, detect_scenes

    tmp = Path(tempfile.mkdtemp(prefix="agora-scenes-"))

    def build(path: Path, segments: list[tuple[str, int]]) -> None:
        inputs: list[str] = []
        for colour, secs in segments:
            inputs += ["-f", "lavfi", "-t", str(secs), "-i", f"color=c={colour}:s=320x240:r=25"]
        filt = "".join(f"[{i}:v]" for i in range(len(segments)))
        filt += f"concat=n={len(segments)}:v=1:a=0[v]"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", *inputs,
             "-filter_complex", filt, "-map", "[v]",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
            capture_output=True, timeout=180, check=True,
        )

    # ── Случай 1: четыре плана по четыре секунды ────────────────────────────
    #
    # Четыре, а не две: одна склейка нашлась бы и случайно. Четыре секунды на
    # план, а не две, — чтобы ни одна граница не была отброшена правилом
    # MIN_SCENE_SEC и провал детектора нельзя было списать на него.
    cut_video = tmp / "cuts.mp4"
    build(cut_video, [("red", 4), ("lime", 4), ("blue", 4), ("yellow", 4)])
    scenes = detect_scenes(cut_video)
    starts = [round(s.start_sec, 1) for s in scenes]

    expected = [0.0, 4.0, 8.0, 12.0]
    matched = all(
        any(abs(start - e) <= 0.5 for start in starts) for e in expected
    )
    check(
        CASES[0],
        matched and len(starts) == len(expected),
        f"ожидались границы {expected}, получены {starts}",
    )

    # ── Случай 2: непрерывный ролик длиннее потолка ─────────────────────────
    flat_video = tmp / "flat.mp4"
    build(flat_video, [("red", int(MAX_SCENE_SEC) + 10)])
    flat = detect_scenes(flat_video)
    longest = max((s.end_sec - s.start_sec for s in flat), default=0.0)

    check(
        CASES[1],
        len(flat) > 1 and longest <= MAX_SCENE_SEC + 0.5,
        f"сцен {len(flat)}, самая длинная {longest:.1f}с при потолке {MAX_SCENE_SEC}",
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
