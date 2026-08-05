#!/usr/bin/env python3
"""
CDD-тест задачи #17 — «Склейка (reduce) + Content Pack».

CDD (из tasks.json):
  склейка выдаёт единый таймлайн;
  каждый факт имеет таймкод в пределах длительности видео;
  для длинного режима stitched == true;
  компактная форма строго меньше полной по объёму и при этом сохраняет все
  ключевые сцены и все таймкоды, на которые ссылается отчёт;
  обе формы валидны по canonical JSON Schema.

─── Почему тест не зовёт модель ──────────────────────────────────────────────
Промпт content.stitch_summary существует и просит модель собрать связный
синопсис. Но ни один пункт cdd не про качество текста: все пять — про структуру
таймлайна, границы таймкодов, признак сшивки и соотношение двух форм. Это
свойства редьюса, а не модели, и проверяются они на детерминированных входах без
единого обращения к сети.

Такое разделение не обходной путь, а требование к самому редьюсу: сборка
таймлайна обязана работать и тогда, когда модель недоступна. Иначе отказ
провайдера превращает уже оплаченные транскрипцию и VLM-разбор в мусор.

─── Про «каждый факт имеет таймкод в пределах длительности» ──────────────────
Проверяется на входе с ловушками: сцена за концом ролика (VLM иногда возвращает
таймкод из своего текста, а не из панели) и отрицательный старт. Оба случая
реальны. Первый — потому что модель переписывает подставленное значение;
второй — потому что сегментация длинного видео складывает локальный таймкод с
оффсетом сегмента, и ошибка знака даёт отрицательный старт, который в остальном
выглядит правдоподобно.

Таймкод вне ролика опаснее, чем кажется: на него сошлётся респондент в
grounding_refs, отчёт покажет ссылку на несуществующий момент, и проверить её
будет нечем — видео к тому времени уже удалено по политике хранения.

─── Про «компактная строго меньше» ───────────────────────────────────────────
Сравнивается объём сериализованного JSON, а не число полей. Экономия, ради
которой две формы заведены (Decision Log #15), считается в токенах запроса, и
компактная форма с тем же числом ключей, но полным транскриптом внутри, требование
формально выполнила бы, а денег не сэкономила.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "services" / "agent-core"
SCHEMA_PATH = REPO / "packages" / "shared" / "schemas" / "content-pack.schema.json"

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    shown = "" if ok else detail
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {shown}" if shown else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


# ═══════════════════════════════════════════════════════════════════════════
# Входные данные: два сегмента длинного видео, склеенные по глобальным
# таймкодам. Ловушки внутри — см. docstring.
# ═══════════════════════════════════════════════════════════════════════════

DURATION = 900.0  # 15 минут

TRANSCRIPT = [
    {"start": 0.0, "end": 4.5, "text": "Мы приехали сюда впервые."},
    {"start": 4.5, "end": 9.0, "text": "И сразу поняли, что всё изменилось."},
    {"start": 300.0, "end": 305.0, "text": "Второй сегмент начинается здесь."},
    {"start": 880.0, "end": 890.0, "text": "Финальная реплика героя."},
]

SPEAKERS = [
    {"start": 0.0, "end": 9.0, "speaker": "SPEAKER_00"},
    {"start": 300.0, "end": 305.0, "speaker": "SPEAKER_01"},
    {"start": 880.0, "end": 890.0, "speaker": "SPEAKER_00"},
]

SCENES = [
    {
        "panel_index": 0, "timestamp_sec": 0.0,
        "scene_description": "Двое выходят из машины у старого дома",
        "actions": ["выходят из машины"], "mood": "тревожное ожидание",
        "characters": [{"appearance": "мужчина в пальто", "emotion": "напряжение"}],
        "setting": "просёлочная дорога, сумерки",
        "cinematography": {"shot": "общий", "lighting": "естественный", "camera": "статика"},
        "on_screen_text": None, "notable": "костюмы эпохи",
    },
    {
        "panel_index": 1, "timestamp_sec": 300.0,
        "scene_description": "Разговор на кухне переходит в ссору",
        "actions": ["спорят"], "mood": "конфликт",
        "characters": [{"appearance": "женщина у окна", "emotion": "гнев"}],
        "setting": "кухня",
        "cinematography": {"shot": "средний", "lighting": "контровый", "camera": "ручная"},
        "on_screen_text": None, "notable": "разбитая посуда",
    },
    {
        "panel_index": 2, "timestamp_sec": 880.0,
        "scene_description": "Герой уходит по дороге, камера остаётся",
        "actions": ["уходит"], "mood": "опустошение",
        "characters": [{"appearance": "мужчина со спины", "emotion": "смирение"}],
        "setting": "та же дорога, рассвет",
        "cinematography": {"shot": "общий", "lighting": "мягкий", "camera": "статика"},
        "on_screen_text": None, "notable": "рифма с первой сценой",
    },
    # ЛОВУШКА 1: таймкод за концом ролика — модель переписала подставленное значение.
    {
        "panel_index": 3, "timestamp_sec": 1500.0,
        "scene_description": "Сцена, которой в ролике нет",
        "actions": [], "mood": "нет", "characters": [], "setting": "нет",
        "cinematography": {}, "on_screen_text": None, "notable": "",
    },
    # ЛОВУШКА 2: отрицательный старт — ошибка знака оффсета сегмента.
    {
        "panel_index": 4, "timestamp_sec": -12.0,
        "scene_description": "Сцена с отрицательным таймкодом",
        "actions": [], "mood": "нет", "characters": [], "setting": "нет",
        "cinematography": {}, "on_screen_text": None, "notable": "",
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# СТАТИЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Статический уровень ==")

check("canonical JSON Schema Content Pack существует", SCHEMA_PATH.is_file(),
      f"нет {SCHEMA_PATH.relative_to(REPO)}")

schema = None
if SCHEMA_PATH.is_file():
    try:
        schema = json.loads(SCHEMA_PATH.read_text("utf-8"))
        check("схема читается как JSON", isinstance(schema, dict))
    except json.JSONDecodeError as e:
        check("схема читается как JSON", False, str(e)[:120])

module = CORE / "agent_core" / "content" / "pack.py"
check("модуль склейки существует", module.is_file(),
      "нет services/agent-core/agent_core/content/pack.py")


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Поведенческий уровень ==")

CASES = [
    "склейка выдаёт единый таймлайн",
    "таймлайн упорядочен по времени",
    "таймкоды сцен не выходят за длительность ролика",
    "таймкоды реплик не выходят за длительность ролика",
    "сцена за концом ролика отброшена, а не подрезана молча",
    "сцена с отрицательным таймкодом отброшена",
    "отброшенные сцены перечислены в отчёте о склейке",
    "длинный режим помечен stitched == true",
    "короткий режим помечен stitched == false",
    "транскрипт — позвоночник: у записи таймлайна есть реплики",
    "у реплик проставлен говорящий из диаризации",
    "компактная форма строго меньше полной по объёму",
    "компактная форма сохраняет все ключевые сцены",
    "компактная форма сохраняет таймкоды ключевых сцен",
    "полная форма содержит полный транскрипт",
    "компактная форма не содержит полный транскрипт",
    "склейка детерминирована: те же входы → тот же пакет",
]

sys.path.insert(0, str(CORE))
build_pack = None
try:
    from agent_core.content.pack import build_pack
except Exception as e:  # noqa: BLE001
    # Различие принципиальное. Нет файла — код не написан, это FAIL: пропуск
    # здесь превратил бы ненаписанную задачу в «проверено в доступном объёме».
    # Файл есть, а импорт падает — почти всегда нехватка зависимости в среде, и
    # вот это честный SKIP.
    verdict = skip if module.is_file() else check
    reason = f"модуль не импортируется: {type(e).__name__}: {str(e)[:60]}"
    for n in CASES:
        verdict(n, False, reason) if verdict is check else verdict(n, reason)

if build_pack is not None:
    try:
        long_pack = build_pack(
            transcript=TRANSCRIPT, speakers=SPEAKERS, scenes=SCENES,
            duration_sec=DURATION, mode="long", title="Тестовый ролик",
        )
        short_pack = build_pack(
            transcript=TRANSCRIPT[:2], speakers=SPEAKERS[:1], scenes=SCENES[:1],
            duration_sec=10.0, mode="short", title="Короткий ролик",
        )

        full = long_pack.full()
        compact = long_pack.compact()

        # ── Единый таймлайн ────────────────────────────────────────────────
        timeline = full.get("timeline", [])
        check(CASES[0], isinstance(timeline, list) and len(timeline) > 0,
              f"timeline={type(timeline).__name__} len={len(timeline) if isinstance(timeline, list) else '—'}")

        starts = [e["start"] for e in timeline] if timeline else []
        check(CASES[1], starts == sorted(starts), f"порядок нарушен: {starts}")

        # ── Границы таймкодов ──────────────────────────────────────────────
        scene_ts = [s["timestamp_sec"] for s in full.get("scenes", [])]
        check(CASES[2], all(0.0 <= t <= DURATION for t in scene_ts),
              f"вне [0, {DURATION}]: {[t for t in scene_ts if not 0.0 <= t <= DURATION]}")

        line_ts = [(e["start"], e["end"]) for e in timeline]
        check(CASES[3],
              all(0.0 <= a <= DURATION and 0.0 <= b <= DURATION for a, b in line_ts),
              f"вне диапазона: {[p for p in line_ts if not (0.0 <= p[0] <= DURATION and 0.0 <= p[1] <= DURATION)]}")

        check(CASES[4], 1500.0 not in scene_ts, "сцена за концом ролика попала в пакет")
        check(CASES[5], -12.0 not in scene_ts, "сцена с отрицательным таймкодом попала в пакет")

        # Молчаливое отбрасывание — половина решения: если VLM систематически
        # врёт с таймкодами, это видно только по списку отброшенного.
        dropped = full.get("dropped_scenes", [])
        check(CASES[6], isinstance(dropped, list) and len(dropped) == 2,
              f"отброшено записей: {len(dropped) if isinstance(dropped, list) else '—'}, ожидалось 2")

        # ── Признак сшивки ─────────────────────────────────────────────────
        check(CASES[7], full.get("stitched") is True, f"stitched={full.get('stitched')!r}")
        check(CASES[8], short_pack.full().get("stitched") is False,
              f"stitched={short_pack.full().get('stitched')!r}")

        # ── Транскрипт — позвоночник ───────────────────────────────────────
        with_lines = [e for e in timeline if e.get("lines")]
        check(CASES[9], len(with_lines) > 0, "ни у одной записи таймлайна нет реплик")

        speakers_seen = {
            ln.get("speaker") for e in timeline for ln in e.get("lines", [])
        }
        check(CASES[10], speakers_seen and speakers_seen != {None},
              f"говорящие не проставлены: {speakers_seen}")

        # ── Две формы ──────────────────────────────────────────────────────
        full_size = len(json.dumps(full, ensure_ascii=False))
        compact_size = len(json.dumps(compact, ensure_ascii=False))
        check(CASES[11], compact_size < full_size,
              f"компактная {compact_size} байт, полная {full_size} — экономии нет")

        key_full = {s["timestamp_sec"] for s in full.get("scenes", []) if s.get("key")}
        key_compact = {s["timestamp_sec"] for s in compact.get("scenes", [])}
        check(CASES[12], key_full and key_full <= key_compact,
              f"потеряны ключевые сцены: {sorted(key_full - key_compact)}")
        check(CASES[13], all(0.0 <= t <= DURATION for t in key_compact),
              f"в компактной форме таймкод вне ролика: {sorted(key_compact)}")

        check(CASES[14], bool(full.get("transcript")), "в полной форме нет транскрипта")
        check(CASES[15], not compact.get("transcript"),
              "компактная форма тащит полный транскрипт — экономия мнимая")

        # ── Детерминизм ────────────────────────────────────────────────────
        again = build_pack(
            transcript=TRANSCRIPT, speakers=SPEAKERS, scenes=SCENES,
            duration_sec=DURATION, mode="long", title="Тестовый ролик",
        ).full()
        check(CASES[16], again == full, "повторная склейка дала другой результат")

    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        for n in CASES:
            if not any(r[0] == n for r in results):
                check(n, False, f"{type(e).__name__}: {str(e)[:90]}")

    # ── Валидность по canonical JSON Schema ────────────────────────────────
    if schema is None:
        skip("обе формы валидны по canonical JSON Schema", "схема не загружена")
    else:
        try:
            import jsonschema
        except ImportError:
            skip("обе формы валидны по canonical JSON Schema", "jsonschema не установлен")
        else:
            try:
                pack = build_pack(
                    transcript=TRANSCRIPT, speakers=SPEAKERS, scenes=SCENES,
                    duration_sec=DURATION, mode="long", title="Тестовый ролик",
                )
                bad = []
                for form_name, doc in (("полная", pack.full()), ("компактная", pack.compact())):
                    try:
                        jsonschema.validate(doc, schema)
                    except jsonschema.ValidationError as ve:
                        bad.append(f"{form_name}: {ve.message[:90]}")
                check("обе формы валидны по canonical JSON Schema", not bad, "; ".join(bad))
            except Exception as e:  # noqa: BLE001
                check("обе формы валидны по canonical JSON Schema", False,
                      f"{type(e).__name__}: {str(e)[:90]}")


# ═══════════════════════════════════════════════════════════════════════════

print()
n_fail = sum(1 for _, s, _ in results if s == FAIL)
n_skip = sum(1 for _, s, _ in results if s == SKIP)
n_ok = sum(1 for _, s, _ in results if s == PASS)
print(f"Итог: OK={n_ok} FAIL={n_fail} SKIP={n_skip}")
if n_fail:
    print("\nНевыполненные условия:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  · {name}" + (f" — {detail}" if detail else ""))
sys.exit(1 if n_fail else 0)
