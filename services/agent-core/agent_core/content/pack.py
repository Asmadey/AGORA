"""
Склейка (reduce) и Content Pack в двух формах — задача #17.

Вход: транскрипт с таймкодами (#15), реплики говорящих (#15) и разбор сцен
VLM (#16). Выход: единый таймлайн по глобальным таймкодам плюс две формы
пакета — полная и компактная (Decision Log #15).

─── Транскрипт — позвоночник ─────────────────────────────────────────────────
Таймлайн строится от реплик, а сцены прикрепляются к ним по таймкоду, а не
наоборот. Причина в плотности: реплики идут секундами, разбор сцен — десятками
секунд (одна панель на сцену после дедупликации). Таймлайн, построенный от
сцен, потерял бы порядок реплик внутри сцены, а именно на реплики ссылаются
респонденты, когда объясняют впечатление.

Есть и вторая причина, менее очевидная. Транскрипт получен из proxy локально и
достоверен; разбор сцен получен от модели и достоверен наполовину — она может
переписать таймкод, придумать действие, пропустить панель. Строить каркас на
менее надёжном источнике значит переносить его ошибки на всю структуру.

─── Границы таймкодов ────────────────────────────────────────────────────────
Всё, что не попадает в [0, duration_sec], выбрасывается и записывается в
dropped_scenes с причиной. Подрезать по границе (clamp) было бы хуже: сцена с
таймкодом 1500 при ролике в 900 секунд — это не «чуть за краем», а признак того,
что модель вернула выдуманное значение, и приклеивать её к финалу значит выдать
выдумку за факт о концовке.

Молчаливое отбрасывание тоже не годится. Если VLM систематически врёт с
таймкодами, увидеть это можно только по списку выброшенного: к моменту разбора
отчёта исходное видео уже удалено по политике хранения, и сверить не с чем.

─── Две формы ────────────────────────────────────────────────────────────────
Компактная уходит в массовый прогон респондентов, полная — контрольной
подвыборке (Decision Log #15). При 500 респондентах разница измеряется разами
стоимости запуска, а не процентами, поэтому «компактная» здесь означает реально
меньший объём сериализованного JSON, а не тот же объём с меньшим числом ключей.

Основную экономию даёт отказ от полного транскрипта: он линеен по длительности,
тогда как число ключевых сцен растёт много медленнее.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: Сколько ключевых сцен максимум оставляет сжатие. Потолок нужен ролику на час:
#: там сцен сотни, и «только ключевые» без потолка всё равно даёт пакет, который
#: незачем слать пятистам респондентам.
MAX_KEY_SCENES = 12

#: Реплики короче этого не попадают в компактный таймлайн: «Да», «Ага», «Что?»
#: не несут содержания, а места в запросе занимают наравне с остальными.
MIN_COMPACT_LINE_CHARS = 12


def _num(value: Any) -> float | None:
    """Число или None. Модель возвращает таймкод и строкой, и числом, и мусором."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _speaker_at(turns: list[dict[str, Any]], start: float, end: float) -> str | None:
    """
    Кто говорит на отрезке [start, end].

    Берётся реплика с наибольшим перекрытием, а не первая подходящая. На стыке
    говорящих реплика транскрипта регулярно задевает обе, и «первая подходящая»
    отдала бы её тому, кто успел сказать полслова, — с равной вероятностью
    правильному и неправильному.
    """
    best: str | None = None
    best_overlap = 0.0
    for turn in turns:
        t_start, t_end = _num(turn.get("start")), _num(turn.get("end"))
        if t_start is None or t_end is None:
            continue
        overlap = min(end, t_end) - max(start, t_start)
        if overlap > best_overlap:
            best_overlap = overlap
            best = turn.get("speaker")
    return best


@dataclass
class ContentPack:
    """
    Склеенный материал. Формы получаются методами full() и compact().

    Хранит одно состояние и отдаёт два представления, а не два готовых словаря:
    иначе компактная форма могла бы разойтись с полной по фактам, и расхождение
    выглядело бы как разница восприятия контрольной подвыборки и массового
    прогона — то есть как содержательный вывод исследования.
    """

    title: str
    duration_sec: float
    stitched: bool
    timeline: list[dict[str, Any]] = field(default_factory=list)
    scenes: list[dict[str, Any]] = field(default_factory=list)
    transcript: list[dict[str, Any]] = field(default_factory=list)
    dropped_scenes: list[dict[str, Any]] = field(default_factory=list)

    # ── Полная форма ────────────────────────────────────────────────────────

    def full(self) -> dict[str, Any]:
        """Всё: полный транскрипт, все сцены, весь таймлайн."""
        return {
            "form": "full",
            "title": self.title,
            "duration_sec": self.duration_sec,
            "stitched": self.stitched,
            "timeline": self.timeline,
            "scenes": self.scenes,
            "transcript": self.transcript,
            "dropped_scenes": self.dropped_scenes,
            "stats": self._stats(),
        }

    # ── Компактная форма ────────────────────────────────────────────────────

    def compact(self) -> dict[str, Any]:
        """
        Сжатая форма для массового прогона.

        Выбрасывается: полный транскрипт, неключевые сцены, детали разбора
        (кадр, свет, костюмы) и короткие реплики. Остаётся то, на что респондент
        может сослаться в grounding_refs: ключевые сцены с таймкодами и реплики,
        несущие содержание.

        dropped_scenes сюда НЕ переносится: это диагностика склейки, нужная
        человеку при разборе прогона, а не персоне при просмотре.
        """
        key_scenes = [
            {
                "timestamp_sec": s["timestamp_sec"],
                "scene_description": s["scene_description"],
                "mood": s.get("mood"),
            }
            for s in self.scenes
            if s.get("key")
        ]

        # Таймлайн сжимается до ключевых сцен, а не только чистится от коротких
        # реплик. Это выяснилось замером: фильтрация реплик внутри полного
        # таймлайна давала экономию в 1.95 раза на пятнадцатиминутном ролике,
        # потому что основную массу составляют сами реплики, а их в неключевых
        # сценах столько же, сколько в ключевых.
        #
        # Экономия «в разы, а не в процентах» (Decision Log #15) требует убрать
        # неключевые записи целиком. Респондент при этом не теряет опоры: всё,
        # на что он может сослаться в grounding_refs, — это ключевые сцены,
        # которые здесь и остаются вместе со своими репликами.
        key_starts = {s["timestamp_sec"] for s in self.scenes if s.get("key")}

        compact_timeline = []
        for entry in self.timeline:
            # Запись до первой сцены (scene is None) сохраняется: там завязка,
            # на которую ссылаются, объясняя первое впечатление.
            is_key = entry.get("scene") is None or entry["start"] in key_starts
            if not is_key:
                continue
            lines = [
                ln for ln in entry["lines"]
                if len(ln["text"]) >= MIN_COMPACT_LINE_CHARS
            ]
            if not lines and not entry.get("scene"):
                continue
            compact_timeline.append({
                "start": entry["start"],
                "end": entry["end"],
                "scene": entry.get("scene"),
                "mood": entry.get("mood"),
                "lines": lines,
            })

        return {
            "form": "compact",
            "title": self.title,
            "duration_sec": self.duration_sec,
            "stitched": self.stitched,
            "timeline": compact_timeline,
            "scenes": key_scenes,
            "stats": self._stats(),
        }

    def _stats(self) -> dict[str, Any]:
        speakers = {
            ln.get("speaker")
            for entry in self.timeline
            for ln in entry["lines"]
            if ln.get("speaker")
        }
        return {
            "scenes_total": len(self.scenes),
            "scenes_key": sum(1 for s in self.scenes if s.get("key")),
            "lines_total": sum(len(e["lines"]) for e in self.timeline),
            "speakers": len(speakers),
        }

    def size_ratio(self) -> float:
        """Во сколько раз компактная форма меньше полной. Для отчёта о стоимости."""
        full_len = len(json.dumps(self.full(), ensure_ascii=False))
        compact_len = len(json.dumps(self.compact(), ensure_ascii=False))
        return full_len / compact_len if compact_len else 1.0


# ─── Сборка ──────────────────────────────────────────────────────────────────


def build_pack(
    *,
    transcript: list[dict[str, Any]],
    speakers: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    duration_sec: float,
    mode: str,
    title: str,
) -> ContentPack:
    """
    Сводит транскрипт, диаризацию и разбор сцен в Content Pack.

    Детерминирована: одни и те же входы дают побайтово одинаковый пакет. Это не
    роскошь — на повторном прогоне исследования (#30) материал тот же, и
    расхождение пакета означало бы, что разница в ответах персон вызвана
    обработкой, а не новыми вопросами.

    `mode` — "short" | "long". Длинный режим означает сегментированную обработку,
    и stitched выставляется по нему, а не по числу сцен: ролик на 12 минут с
    одной сценой всё равно собран из сегментов.
    """
    valid_scenes: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    for scene in scenes:
        ts = _num(scene.get("timestamp_sec"))
        if ts is None:
            dropped.append({
                "timestamp_sec": 0.0,
                "panel_index": scene.get("panel_index"),
                "reason": "таймкод отсутствует или не разбирается как число",
            })
            continue
        if ts < 0:
            dropped.append({
                "timestamp_sec": ts,
                "panel_index": scene.get("panel_index"),
                "reason": "отрицательный таймкод — вероятна ошибка знака оффсета сегмента",
            })
            continue
        if ts > duration_sec:
            dropped.append({
                "timestamp_sec": ts,
                "panel_index": scene.get("panel_index"),
                "reason": (
                    f"таймкод {ts:.1f} за концом ролика ({duration_sec:.1f}) — "
                    "модель вернула значение из текста, а не из панели"
                ),
            })
            continue
        valid_scenes.append({**scene, "timestamp_sec": ts})

    valid_scenes.sort(key=lambda s: s["timestamp_sec"])

    # ── Транскрипт: отсечение по границам и проставление говорящего ─────────
    lines: list[dict[str, Any]] = []
    for seg in transcript:
        start, end = _num(seg.get("start")), _num(seg.get("end"))
        text = (seg.get("text") or "").strip()
        if start is None or end is None or not text:
            continue
        if start < 0 or start > duration_sec:
            continue
        # Хвост последней реплики регулярно выходит за длительность на доли
        # секунды: Whisper округляет конец сегмента вверх. Это не выдумка модели,
        # а свойство декодера, поэтому конец подрезается, а не отбрасывается.
        end = min(end, duration_sec)
        lines.append({
            "start": start,
            "end": end,
            "text": text,
            "speaker": _speaker_at(speakers, start, end),
        })

    lines.sort(key=lambda ln: ln["start"])

    # ── Таймлайн: реплики группируются по ближайшей предшествующей сцене ────
    timeline = _build_timeline(lines, valid_scenes, duration_sec)

    _mark_key_scenes(valid_scenes, timeline)

    return ContentPack(
        title=title,
        duration_sec=duration_sec,
        stitched=(mode == "long"),
        timeline=timeline,
        scenes=valid_scenes,
        transcript=lines,
        dropped_scenes=dropped,
    )


def _build_timeline(
    lines: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    duration_sec: float,
) -> list[dict[str, Any]]:
    """
    Строит единый таймлайн: по записи на сцену, реплики внутри.

    Реплики, прозвучавшие до первой сцены, не выбрасываются — под них заводится
    запись без сцены. Потерять начало разговора значило бы потерять завязку, а
    именно на неё чаще всего ссылаются, объясняя первое впечатление.
    """
    if not scenes:
        return (
            [{
                "start": lines[0]["start"],
                "end": lines[-1]["end"],
                "scene": None,
                "mood": None,
                "lines": lines,
            }]
            if lines else []
        )

    bounds: list[tuple[float, float, dict[str, Any] | None]] = []
    if lines and lines[0]["start"] < scenes[0]["timestamp_sec"]:
        bounds.append((lines[0]["start"], scenes[0]["timestamp_sec"], None))
    for i, scene in enumerate(scenes):
        start = scene["timestamp_sec"]
        end = scenes[i + 1]["timestamp_sec"] if i + 1 < len(scenes) else duration_sec
        bounds.append((start, end, scene))

    timeline: list[dict[str, Any]] = []
    for start, end, scene in bounds:
        # Полуинтервал [start, end): реплика на самой границе принадлежит
        # следующей сцене, иначе она попала бы в обе и посчиталась дважды.
        # Последняя запись включает правую границу, иначе финальная реплика,
        # заканчивающаяся ровно на длительности, потерялась бы.
        is_last = (start, end, scene) == bounds[-1]
        entry_lines = [
            ln for ln in lines
            if start <= ln["start"] < end or (is_last and ln["start"] == end)
        ]
        timeline.append({
            "start": start,
            "end": end,
            "scene": scene.get("scene_description") if scene else None,
            "mood": scene.get("mood") if scene else None,
            "lines": entry_lines,
        })
    return timeline


def _mark_key_scenes(scenes: list[dict[str, Any]], timeline: list[dict[str, Any]]) -> None:
    """
    Помечает сцены, которые переживут сжатие.

    Отбор по трём признакам, и все три — про то, на что респондент сошлётся,
    объясняя впечатление:

      · первая и последняя сцены — завязка и финал;
      · смена настроения относительно предыдущей сцены — эмоциональный пик,
        то есть место, где впечатление меняется;
      · плотность реплик — сцена, вокруг которой больше всего говорят.

    Признаки считаются по материалу, а не спрашиваются у модели. Отдать отбор
    ключевых сцен модели значило бы поставить экономию массового прогона в
    зависимость от вызова, который сам стоит денег и может не ответить.
    """
    if not scenes:
        return

    lines_by_ts = {
        entry["start"]: len(entry["lines"])
        for entry in timeline
        if entry.get("scene") is not None
    }
    if lines_by_ts:
        busiest = sorted(lines_by_ts.items(), key=lambda kv: (-kv[1], kv[0]))
        dense = {ts for ts, count in busiest[:MAX_KEY_SCENES] if count > 0}
    else:
        dense = set()

    prev_mood = None
    for i, scene in enumerate(scenes):
        mood = scene.get("mood")
        is_edge = i == 0 or i == len(scenes) - 1
        mood_shift = prev_mood is not None and mood != prev_mood
        scene["key"] = bool(is_edge or mood_shift or scene["timestamp_sec"] in dense)
        prev_mood = mood

    # Потолок: держим границы ролика и самые плотные сцены, остальные снимаем.
    keyed = [s for s in scenes if s["key"]]
    if len(keyed) > MAX_KEY_SCENES:
        protected = {scenes[0]["timestamp_sec"], scenes[-1]["timestamp_sec"]}
        ranked = sorted(
            keyed,
            key=lambda s: (
                s["timestamp_sec"] not in protected,
                -lines_by_ts.get(s["timestamp_sec"], 0),
                s["timestamp_sec"],
            ),
        )
        survivors = {s["timestamp_sec"] for s in ranked[:MAX_KEY_SCENES]}
        for scene in scenes:
            scene["key"] = scene["timestamp_sec"] in survivors
