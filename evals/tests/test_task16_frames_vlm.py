#!/usr/bin/env python3
"""
CDD-тест задачи #16 — Нарезка кадров + VLM-разбор.

CDD (из tasks.json):
  PySceneDetect на fixture даёт сцены;
  при нуле сцен срабатывает fallback-интервал;
  на статичной сцене дедупликация сокращает число кадров, а на динамичной
  не выбрасывает различающиеся;
  повторный прогон берёт кэш (0 новых вызовов VLM);
  кап вызовов из Настроек соблюдается.

Двухуровневый. Статический разбирает исходники и работает где угодно.
Поведенческий требует ffmpeg (нарезка кадров) и PySceneDetect (сцены) — без них
честный SKIP, а не выдуманный результат.

─── Почему ни один уровень не вызывает модель ────────────────────────────────
Все пять пунктов cdd — про то, СКОЛЬКО раз и при каких условиях вызывается VLM,
а не про то, что она отвечает. Кэш проверяется числом вызовов, кап — числом
вызовов, дедупликация — числом кадров, дошедших до вызова. Настоящая модель тут
ничего не добавляет, а гейт CANARY (не больше трёх вызовов) тратит.

Поэтому analyze_panels обязан принимать клиента параметром. Это не уступка
тестам: тот же шов нужен продукту, чтобы развести разбор кадров и рассуждение
персон по разным агентам провайдера (см. ModelConfig.vlm_shares_agent).
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "services" / "agent-core"
FRAMES_DIR = CORE / "agent_core" / "frames"

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


def src(name: str) -> str:
    p = FRAMES_DIR / name
    return p.read_text("utf-8") if p.exists() else ""


# ═══════════════════════════════════════════════════════════════════════════
# СТАТИЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Статический уровень ==")

check("модуль agent_core.frames существует", (FRAMES_DIR / "__init__.py").exists())

init_src = src("__init__.py")
scenes_src = src("scenes.py")
dedup_src = src("dedup.py")
analyze_src = src("analyze.py")
all_src = init_src + scenes_src + dedup_src + analyze_src

check("scenes.py существует", bool(scenes_src))
check("dedup.py существует", bool(dedup_src))
check("analyze.py существует", bool(analyze_src))

check(
    "детекция сцен использует PySceneDetect, а не свою эвристику",
    "scenedetect" in scenes_src,
)

# Fallback обязан быть именованной константой, а не числом в глубине функции:
# интервал определяет, сколько кадров уедет в VLM на ролике без монтажных
# склеек, то есть напрямую задаёт стоимость прогона.
check(
    "интервал fallback объявлен константой",
    "FALLBACK_INTERVAL" in scenes_src,
)

# Дедупликация по перцептивному хешу, а не по равенству байтов. Два соседних
# кадра статичной сцены почти никогда не совпадают побайтово — шум кодека
# меняет пиксели, — поэтому побайтовое сравнение не выбросило бы ни одного
# кадра и дедупликация выглядела бы работающей, ничего не делая.
check(
    "дедупликация считает перцептивный хеш",
    "dhash" in dedup_src or "phash" in dedup_src,
)
check(
    "близость кадров меряется расстоянием Хэмминга, а не равенством",
    "hamming" in dedup_src.lower(),
)

check("размер панели объявлен константой", "PANEL_SIZE" in all_src)

# Клиент передаётся параметром — см. шапку файла.
check(
    "analyze_panels принимает клиента параметром",
    "client" in analyze_src and "def analyze_panels" in analyze_src,
)

# Ключ кэша обязан зависеть от шаблона промпта и модели, а не только от кадров.
# Иначе правка content.frame_analysis в Промпт-студии (#26) молча вернёт разбор,
# сделанный по прежнему шаблону: пользователь увидит, что промпт изменён, а
# результат — нет, и объяснить это будет нечем.
check(
    "ключ кэша учитывает шаблон промпта",
    "prompt" in analyze_src and "cache_key" in analyze_src,
)
check(
    "ключ кэша учитывает модель",
    "model" in analyze_src,
)

# Decision Log #17: отдельный OCR-контур не вводится. Проверка держит решение,
# а не комментарий о нём.
check(
    "отдельный OCR-контур не заведён (Decision Log #17)",
    not any(w in all_src.lower() for w in ("tesseract", "easyocr", "paddleocr")),
)

# Кап приходит снимком настроек задачи, как и модель Whisper (#15). Читать
# настройки на лету нельзя: пока задача стоит в очереди, команда может сменить
# кап, и тогда половина панелей разобрана под одним потолком, половина под
# другим — расхождение, которое ничем не объяснить.
check(
    "кап берётся из снимка настроек задачи, а не только из env",
    "for_task" in analyze_src,
)

check(
    "PySceneDetect объявлен в зависимостях",
    "scenedetect" in (CORE / "pyproject.toml").read_text("utf-8"),
)

# Сборка opencv проверяется по факту установки, а не по строке в pyproject.
#
# Спек `scenedetect[opencv-headless]` выглядит правильным и на 0.7.x не работает:
# экстру там убрали, а opencv-python сделали базовой зависимостью. pip в этом
# случае печатает предупреждение и ставит полную GUI-сборку — образ воркера
# (python:3.13-slim, без libGL) упал бы при первом импорте, уже на проде.
#
# Поэтому проверка смотрит, какой дистрибутив стоит фактически: она переживёт
# и поднятие потолка версии, и переезд на другой пакет.
if importlib.util.find_spec("cv2") is None:
    skip("установлена headless-сборка opencv, а не GUI", "opencv не установлен")
else:
    import importlib.metadata as _meta

    installed = {d.metadata["Name"].lower() for d in _meta.distributions()
                 if d.metadata["Name"]}
    check(
        "установлена headless-сборка opencv, а не GUI",
        "opencv-python" not in installed,
        "стоит opencv-python (GUI): в python:3.13-slim нет libGL — воркер упадёт "
        "при первом импорте" if "opencv-python" in installed
        else "opencv-python-headless",
    )


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("\n== Поведенческий уровень ==")

ffmpeg = shutil.which("ffmpeg")
has_scenedetect = importlib.util.find_spec("scenedetect") is not None
module_ready = (FRAMES_DIR / "__init__.py").exists()

SCENE_CASES = (
    "PySceneDetect находит сцены на ролике со склейкой",
    "таймкоды сцен монотонны и лежат в пределах длительности",
    "при нуле сцен срабатывает fallback-интервал",
)
FRAME_CASES = (
    "дедупликация схлопывает повторяющиеся кадры статичной сцены",
    "дедупликация не выбрасывает различающиеся кадры динамичной сцены",
    "мелкое движение на статичном фоне признаётся повтором (замеренный предел)",
    "панели собираются по PANEL_SIZE кадров",
)
VLM_CASES = (
    "первый прогон вызывает VLM по числу панелей",
    "повторный прогон берёт кэш — 0 новых вызовов VLM",
    "правка шаблона промпта делает кэш недействительным",
    "жёсткий кап обрывает разбор на заданном числе вызовов",
    "режим «авто» не ограничивает число вызовов",
)


def skip_all(names: tuple[str, ...], why: str) -> None:
    for n in names:
        skip(n, why)


if not module_ready:
    skip_all(SCENE_CASES + FRAME_CASES + VLM_CASES, "модуль agent_core.frames ещё не реализован")
else:
    sys.path.insert(0, str(CORE))

    # ─── Сцены ────────────────────────────────────────────────────────────
    if not ffmpeg:
        skip_all(SCENE_CASES, "ffmpeg не установлен")
    elif not has_scenedetect:
        skip_all(SCENE_CASES, "PySceneDetect не установлен")
    else:
        from agent_core.frames import FALLBACK_INTERVAL_SEC, detect_scenes

        with tempfile.TemporaryDirectory() as tmp:
            tmpd = Path(tmp)
            cuts = tmpd / "cuts.mp4"
            static = tmpd / "static.mp4"

            # Ролик со склейкой: три визуально несовместимых куска подряд.
            # Резкая смена — то, что детектор обязан найти; плавный переход
            # проверял бы порог, а не сам факт детекции.
            parts = []
            for i, source in enumerate((
                "color=c=black:size=320x240:rate=10:duration=2",
                "color=c=white:size=320x240:rate=10:duration=2",
                "testsrc=size=320x240:rate=10:duration=2",
            )):
                p = tmpd / f"part{i}.mp4"
                subprocess.run(
                    [ffmpeg, "-y", "-f", "lavfi", "-i", source,
                     "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)],
                    capture_output=True, timeout=120,
                )
                parts.append(p)
            listing = tmpd / "list.txt"
            listing.write_text("".join(f"file '{p}'\n" for p in parts), "utf-8")
            subprocess.run(
                [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                 "-c", "copy", str(cuts)],
                capture_output=True, timeout=120,
            )

            # Ролик без склеек: один цвет на всю длину. Детектор обязан вернуть
            # ноль сцен, и тогда включается fallback.
            static_dur = FALLBACK_INTERVAL_SEC * 3
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi",
                 "-i", f"color=c=navy:size=320x240:rate=10:duration={static_dur}",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", str(static)],
                capture_output=True, timeout=180,
            )

            try:
                scenes = detect_scenes(cuts)
                check("PySceneDetect находит сцены на ролике со склейкой",
                      len(scenes) >= 2, f"сцен: {len(scenes)}")

                monotonic = all(
                    a.start_sec <= a.end_sec <= b.start_sec
                    for a, b in zip(scenes, scenes[1:], strict=False)
                )
                within = bool(scenes) and scenes[-1].end_sec <= 6.5
                check("таймкоды сцен монотонны и лежат в пределах длительности",
                      monotonic and within,
                      f"последняя сцена кончается на {scenes[-1].end_sec:.2f}с"
                      if scenes else "сцен нет")
            except Exception as e:  # noqa: BLE001
                check("PySceneDetect находит сцены на ролике со склейкой", False,
                      f"{type(e).__name__}: {str(e)[:90]}")
                check("таймкоды сцен монотонны и лежат в пределах длительности", False,
                      "сцены не получены")

            try:
                flat = detect_scenes(static)
                # Ключевое: без fallback список был бы пуст, и ролик без монтажа
                # уехал бы в разбор нулём кадров — то есть просто не был бы
                # разобран, без единой ошибки.
                expected = static_dur / FALLBACK_INTERVAL_SEC
                check("при нуле сцен срабатывает fallback-интервал",
                      len(flat) >= expected - 1,
                      f"сцен: {len(flat)}, ожидалось ≈{expected:.0f} "
                      f"по интервалу {FALLBACK_INTERVAL_SEC}с")
            except Exception as e:  # noqa: BLE001
                check("при нуле сцен срабатывает fallback-интервал", False,
                      f"{type(e).__name__}: {str(e)[:90]}")

    # ─── Кадры: дедупликация и панели ─────────────────────────────────────
    if not ffmpeg:
        skip_all(FRAME_CASES, "ffmpeg не установлен")
    else:
        from agent_core.frames import PANEL_SIZE, build_panels, dedupe, extract_frames

        with tempfile.TemporaryDirectory() as tmp:
            tmpd = Path(tmp)
            still = tmpd / "still.mp4"
            moving = tmpd / "moving.mp4"
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi",
                 "-i", "color=c=teal:size=320x240:rate=10:duration=4",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", str(still)],
                capture_output=True, timeout=120,
            )
            # Динамичная сцена — та, где меняется ВЕСЬ кадр. `life` с
            # фиксированным посевом детерминирован (проверено двумя прогонами) и
            # даёт попарные расстояния 16–29 при пороге 4 — запас, которого
            # хватает, чтобы проверка мерила свойство, а не удачу округления.
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi",
                 "-i", "life=size=320x240:rate=10:seed=42:mold=10", "-t", "4",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", str(moving)],
                capture_output=True, timeout=120,
            )
            # Мелкое движение на статичном фоне — отдельный случай, см. ниже.
            small_motion = tmpd / "small_motion.mp4"
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi",
                 "-i", "testsrc=size=320x240:rate=10:duration=4",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", str(small_motion)],
                capture_output=True, timeout=120,
            )

            stamps = [0.5, 1.5, 2.5, 3.5]
            try:
                still_frames = extract_frames(still, stamps, tmpd / "still_frames")
                kept = dedupe(still_frames)
                check("дедупликация схлопывает повторяющиеся кадры статичной сцены",
                      len(kept) == 1 and len(still_frames) == len(stamps),
                      f"{len(still_frames)} кадров → {len(kept)}")
            except Exception as e:  # noqa: BLE001
                check("дедупликация схлопывает повторяющиеся кадры статичной сцены",
                      False, f"{type(e).__name__}: {str(e)[:90]}")

            try:
                moving_frames = extract_frames(moving, stamps, tmpd / "moving_frames")
                kept = dedupe(moving_frames)
                check("дедупликация не выбрасывает различающиеся кадры динамичной сцены",
                      len(kept) == len(moving_frames),
                      f"{len(moving_frames)} кадров → {len(kept)}")
            except Exception as e:  # noqa: BLE001
                check("дедупликация не выбрасывает различающиеся кадры динамичной сцены",
                      False, f"{type(e).__name__}: {str(e)[:90]}")

            # Замеренный предел метода, а не дефект. dHash сжимает кадр до 9×8 в
            # оттенках серого, и мелкая движущаяся деталь на неизменном фоне в
            # такой сетке исчезает: у testsrc попарные расстояния 2–8 при пороге
            # 4, то есть часть кадров признаётся повторами.
            #
            # Для продукта это скорее верно, чем нет: «человек говорит в той же
            # комнате» — одна сцена, и четыре её панели дали бы модели один и тот
            # же ответ за четыре вызова. Речь всё равно приходит из транскрипта,
            # а не из кадров. Но случай зафиксирован проверкой, потому что для
            # интервью — самого частого материала в домене — он означает
            # заведомо тонкий video_understanding, и #17 не должен этому
            # удивляться.
            try:
                sm_frames = extract_frames(small_motion, stamps, tmpd / "sm_frames")
                sm_kept = dedupe(sm_frames)
                check("мелкое движение на статичном фоне признаётся повтором "
                      "(замеренный предел)",
                      len(sm_kept) < len(sm_frames),
                      f"{len(sm_frames)} кадров → {len(sm_kept)}; "
                      f"кадры различаются, но не в сетке 9×8")
            except Exception as e:  # noqa: BLE001
                check("мелкое движение на статичном фоне признаётся повтором "
                      "(замеренный предел)", False,
                      f"{type(e).__name__}: {str(e)[:90]}")

            try:
                nine = extract_frames(
                    moving, [i * 0.4 for i in range(9)], tmpd / "nine",
                )
                panels = build_panels(nine)
                sizes = [len(p.frames) for p in panels]
                check("панели собираются по PANEL_SIZE кадров",
                      len(panels) == 3 and sizes[:2] == [PANEL_SIZE, PANEL_SIZE]
                      and sizes[2] == 1,
                      f"9 кадров → панели {sizes} при PANEL_SIZE={PANEL_SIZE}")
            except Exception as e:  # noqa: BLE001
                check("панели собираются по PANEL_SIZE кадров", False,
                      f"{type(e).__name__}: {str(e)[:90]}")

    # ─── VLM: кэш и кап ───────────────────────────────────────────────────
    try:
        from agent_core.frames import (
            CallBudget,
            CostCapExceeded,
            MemoryCache,
            Panel,
            analyze_panels,
        )
    except Exception as e:  # noqa: BLE001
        skip_all(VLM_CASES, f"контракт разбора недоступен: {type(e).__name__}: {str(e)[:60]}")
    else:
        class RecordingClient:
            """Считает вызовы и отвечает валидным JSON сцены.

            Заменяет модель, но не логику вокруг неё: кэш, кап и порядок
            панелей — наши, и именно они здесь проверяются.
            """

            def __init__(self) -> None:
                self.calls = 0

            def analyze(self, *, image: bytes, prompt: str) -> dict:  # noqa: ARG002
                self.calls += 1
                return {"scene_description": f"кадр {self.calls}", "actions": []}

        def make_panels(n: int) -> list[Panel]:
            return [
                Panel(index=i, timestamp_sec=float(i), frames=[], image=f"panel-{i}".encode())
                for i in range(n)
            ]

        PROMPT = "разбери панель {{frames}} на {{timestamp}}"

        # 1. Первый прогон: вызов на каждую панель.
        try:
            client, cache = RecordingClient(), MemoryCache()
            panels = make_panels(3)
            out = analyze_panels(panels, client=client, cache=cache, prompt=PROMPT)
            check("первый прогон вызывает VLM по числу панелей",
                  client.calls == 3 and len(out.scenes) == 3,
                  f"вызовов={client.calls}, сцен={len(out.scenes)}")
        except Exception as e:  # noqa: BLE001
            check("первый прогон вызывает VLM по числу панелей", False,
                  f"{type(e).__name__}: {str(e)[:90]}")

        # 2. Повторный прогон на том же кэше — ни одного нового вызова.
        try:
            client, cache = RecordingClient(), MemoryCache()
            panels = make_panels(3)
            analyze_panels(panels, client=client, cache=cache, prompt=PROMPT)
            first = client.calls
            again = analyze_panels(panels, client=client, cache=cache, prompt=PROMPT)
            check("повторный прогон берёт кэш — 0 новых вызовов VLM",
                  client.calls == first and again.cache_hits == 3,
                  f"вызовов после первого прогона={client.calls - first}, "
                  f"попаданий в кэш={again.cache_hits}")
        except Exception as e:  # noqa: BLE001
            check("повторный прогон берёт кэш — 0 новых вызовов VLM", False,
                  f"{type(e).__name__}: {str(e)[:90]}")

        # 3. Кэш обязан протухать при правке промпта — иначе Промпт-студия
        #    показывает новый шаблон, а разбор приходит по старому.
        try:
            client, cache = RecordingClient(), MemoryCache()
            panels = make_panels(2)
            analyze_panels(panels, client=client, cache=cache, prompt=PROMPT)
            before = client.calls
            analyze_panels(panels, client=client, cache=cache, prompt=PROMPT + " и подробнее")
            check("правка шаблона промпта делает кэш недействительным",
                  client.calls == before + 2,
                  f"новых вызовов после правки промпта: {client.calls - before}")
        except Exception as e:  # noqa: BLE001
            check("правка шаблона промпта делает кэш недействительным", False,
                  f"{type(e).__name__}: {str(e)[:90]}")

        # 4. Жёсткий кап. Молча обрезать нельзя: отчёт построился бы на неполном
        #    разборе, и никто бы об этом не узнал. Настройки (#27) требуют
        #    «реально обрывает пайплайн», значит — исключение с частичным
        #    результатом, а не короткий список.
        try:
            client, cache = RecordingClient(), MemoryCache()
            panels = make_panels(5)
            budget = CallBudget.for_task({"costCap": "hard", "costCapValue": 2})
            try:
                analyze_panels(panels, client=client, cache=cache, prompt=PROMPT,
                               budget=budget)
                check("жёсткий кап обрывает разбор на заданном числе вызовов", False,
                      f"кап не сработал: сделано {client.calls} вызовов при капе 2")
            except CostCapExceeded as e:
                check("жёсткий кап обрывает разбор на заданном числе вызовов",
                      client.calls == 2 and len(getattr(e, "scenes", [])) == 2,
                      f"вызовов={client.calls}, частичных сцен={len(getattr(e, 'scenes', []))}")
        except Exception as e:  # noqa: BLE001
            check("жёсткий кап обрывает разбор на заданном числе вызовов", False,
                  f"{type(e).__name__}: {str(e)[:90]}")

        # 5. «Авто» — дефолт из Настроек — не должен ограничивать ничего.
        try:
            client, cache = RecordingClient(), MemoryCache()
            panels = make_panels(6)
            budget = CallBudget.for_task({"costCap": "auto", "costCapValue": 2})
            out = analyze_panels(panels, client=client, cache=cache, prompt=PROMPT,
                                 budget=budget)
            check("режим «авто» не ограничивает число вызовов",
                  client.calls == 6 and len(out.scenes) == 6,
                  f"вызовов={client.calls} при costCapValue=2 в режиме auto")
        except Exception as e:  # noqa: BLE001
            check("режим «авто» не ограничивает число вызовов", False,
                  f"{type(e).__name__}: {str(e)[:90]}")


sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict  # noqa: E402

sys.exit(verdict(results, "#16"))
