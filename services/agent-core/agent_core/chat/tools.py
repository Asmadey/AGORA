"""
Инструменты чата: модель спрашивает материал, а не получает его целиком.

─── Почему чистки контекста не хватило ──────────────────────────────────────
Этап 0 (`slim_pack`) снял 34.7 % веса и увёл прогон 0091 с 261 103 токенов на
170 613. Это вылечило отказ и не вылечило задачу: 48 минут дали 322 сцены,
двухчасовой фильм даст около восьмисот — одни только сцены займут ~307 000, и
потолок вернётся. Сто персон вместо сорока добавят ещё ~40 000.

Сокращать дальше нечем: всё, что осталось после чистки, — содержание.

─── Что вместо этого ────────────────────────────────────────────────────────
В контексте постоянно живёт ОГЛАВЛЕНИЕ: номер сцены, таймкод, одна фраза. Для
322 сцен это около 8 000 токенов вместо 158 000. Полные описания модель
запрашивает инструментом — по номерам, по диапазону времени или по словам.

Так решается и вторая задача, о которой отказ не сообщал: ответ становится
точнее. Модель смотрит в три нужные сцены вместо того, чтобы тонуть в трёхстах.

Проверено 16.09.2026, что шлюз это умеет: Cloud.ru с Qwen3.6 вернул
`finish_reason=tool_calls` и верно извлёк `{"from_sec": 60, "to_sec": 90}` из
вопроса «что происходит между 60 и 90 секундой».

─── Три правила, на которых всё держится ────────────────────────────────────
**Нумерация одна на весь продукт.** Сцена 47 в оглавлении, сцена 47 на экране
исследования (`Timeline.tsx`, `sceneNumber`) и сцена 47 в ответе модели — одна
и та же сцена. Разошедшаяся нумерация не даёт ошибки: она даёт уверенный ответ
про чужую сцену.

**Обрезка всегда названа.** Инструмент с потолком, молча отдающий часть, хуже
инструмента без потолка: модель считает ответ полным и говорит «таких сцен
всего три», когда их пятьдесят семь. Поэтому `truncated` и `matched` едут в
ответе всегда.

**Изоляция персоны — механизм, а не правило.** В режиме допроса инструменту
НЕЧЕГО вернуть про чужие ответы, даже если модель запросит их по имени. Тот же
приём, что в `persona_context` и `respondent.run.build_slice`, и та же причина:
проверка вывода зелена ровно до первого совпадения формулировок.
"""

from __future__ import annotations

import copy
from typing import Any

#: Сколько сцен инструмент отдаёт за один вызов.
#:
#: Двадцать — это около 10 000 токенов полных описаний на боевом материале
#: (490 токенов на сцену, замер прогона 0091). Больше означает, что модель
#: снова получает материал пачкой вместо ответа на вопрос; меньше — что за
#: сценой из середины придётся ходить трижды.
MAX_SCENES_PER_CALL = 20

#: Сколько реплик отдаётся за один вызов речи.
MAX_LINES_PER_CALL = 120

#: Сколько ответов персон отдаётся за один вызов.
#:
#: Потолок аудитории — 100 персон, и весь набор весит ~66 000 токенов при
#: среднем 661 на персону (замер прогона 0091). Тридцать — это ~20 000.
MAX_ANSWERS_PER_CALL = 30

#: Длина фразы в оглавлении. Оглавление обязано оставаться оглавлением:
#: полное описание сцены — 490 токенов, и 322 таких превратят его обратно в
#: то, от чего мы уходим.
INDEX_SUMMARY_CHARS = 90


def _summary(scene: dict[str, Any]) -> str:
    """Одна фраза о сцене для оглавления."""
    text = str(scene.get("scene_description") or scene.get("notable") or "").strip()
    if len(text) <= INDEX_SUMMARY_CHARS:
        return text
    return text[: INDEX_SUMMARY_CHARS - 1].rstrip() + "…"


def scene_index(pack: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Оглавление: номер, таймкод, одна фраза.

    Нумерация — позиция в `pack["scenes"]`, начиная с единицы. Ровно так же
    нумерует экран (`Timeline.tsx`), и расходиться им нельзя: номер здесь
    существует затем, чтобы человек и модель говорили про одну сцену.

    Таймкод берётся из `time` («0:06–0:16»), а не собирается из секунд: это тот
    самый формат, который засчитывает `has_support`, и второй его источник
    однажды разошёлся бы с первым.
    """
    scenes = pack.get("scenes") or []
    return [
        {"n": n, "time": str(scene.get("time") or ""), "summary": _summary(scene)}
        for n, scene in enumerate(scenes, start=1)
        if isinstance(scene, dict)
    ]


#: Объявления для шлюза. Форма та же, что приняла Cloud.ru при проверке.
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_scenes",
            "description": (
                "Полные описания сцен: что происходит, кто в кадре, как снято, "
                "настроение, текст на экране. Номера берутся из оглавления. "
                "Можно запросить по номерам либо по диапазону времени в секундах."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "numbers": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Номера сцен из оглавления",
                    },
                    "from_sec": {"type": "number", "description": "Начало отрезка, секунды"},
                    "to_sec": {"type": "number", "description": "Конец отрезка, секунды"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_scenes",
            "description": (
                "Найти сцены по словам в описании, действиях, тексте на экране "
                "или обстановке. Возвращает полные описания найденных сцен."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Слова для поиска"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transcript",
            "description": "Реплики из ролика на заданном отрезке времени, с говорящими.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_sec": {"type": "number"},
                    "to_sec": {"type": "number"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_persona_answers",
            "description": (
                "Ответы персон на анкету с их комментариями. Без параметров — "
                "все доступные. В режиме допроса персоны доступны только её "
                "собственные ответы."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "persona_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Идентификаторы персон",
                    },
                },
            },
        },
    },
]


def _numbered(pack: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    return [
        (n, s)
        for n, s in enumerate(pack.get("scenes") or [], start=1)
        if isinstance(s, dict)
    ]


def _cut(items: list[Any], cap: int) -> tuple[list[Any], bool, int]:
    """Обрезка с отчётом. Молчаливая обрезка — худшее, что может сделать потолок."""
    return items[:cap], len(items) > cap, len(items)


def _get_scenes(args: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    numbered = _numbered(pack)
    by_n = dict(numbered)

    raw_numbers = args.get("numbers")
    not_found: list[int] = []

    if isinstance(raw_numbers, list) and raw_numbers:
        picked = []
        for value in raw_numbers:
            try:
                n = int(value)
            except (TypeError, ValueError):
                continue
            if n in by_n:
                picked.append((n, by_n[n]))
            else:
                # Промах по номеру называется. Пустое место в ответе модель
                # прочтёт как «такой сцены не было», а не как «я ошиблась
                # номером».
                not_found.append(n)
    else:
        lo = args.get("from_sec")
        hi = args.get("to_sec")
        if lo is None and hi is None:
            picked = numbered
        else:
            lo = float(lo) if lo is not None else float("-inf")
            hi = float(hi) if hi is not None else float("inf")
            # Пересечение, а не вложенность: сцена 60–95 отвечает на вопрос про
            # отрезок 60–90, хотя целиком в него не помещается.
            picked = [
                (n, s)
                for n, s in numbered
                if float(s.get("timestamp_sec") or 0) < hi
                and float(s.get("end_sec") or 0) > lo
            ]

    cut, truncated, matched = _cut(picked, MAX_SCENES_PER_CALL)
    return {
        "scenes": [{"n": n, **copy.deepcopy(s)} for n, s in cut],
        "truncated": truncated,
        "matched": matched,
        "not_found": not_found,
    }


def _search_scenes(args: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip().lower()
    if not query:
        # Пустой запрос — это «не знаю, что искать», а не «дай всё». Второе
        # прочтение вернуло бы весь материал, ради отказа от которого модуль и
        # написан.
        return {"scenes": [], "truncated": False, "matched": 0, "not_found": []}

    words = [w for w in query.split() if w]
    found = []
    for n, scene in _numbered(pack):
        haystack = " ".join(
            str(scene.get(field) or "")
            for field in ("scene_description", "notable", "on_screen_text", "setting", "mood")
        )
        haystack += " " + " ".join(str(a) for a in (scene.get("actions") or []))
        haystack += " " + " ".join(str(c) for c in (scene.get("characters") or []))
        if all(w in haystack.lower() for w in words):
            found.append((n, scene))

    cut, truncated, matched = _cut(found, MAX_SCENES_PER_CALL)
    return {
        "scenes": [{"n": n, **copy.deepcopy(s)} for n, s in cut],
        "truncated": truncated,
        "matched": matched,
        "not_found": [],
    }


def _get_transcript(args: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    lo = args.get("from_sec")
    hi = args.get("to_sec")
    lo = float(lo) if lo is not None else float("-inf")
    hi = float(hi) if hi is not None else float("inf")

    lines = [
        copy.deepcopy(line)
        for line in (pack.get("transcript") or [])
        if isinstance(line, dict)
        and float(line.get("start") or 0) < hi
        and float(line.get("end") or 0) > lo
    ]
    cut, truncated, matched = _cut(lines, MAX_LINES_PER_CALL)
    return {"lines": cut, "truncated": truncated, "matched": matched}


def _get_persona_answers(
    args: dict[str, Any],
    answers: list[dict[str, Any]],
    persona_id: str | None,
) -> dict[str, Any]:
    def owner(a: dict[str, Any]) -> str:
        return str(a.get("persona_id") or a.get("personaId") or "")

    pool = answers
    if persona_id:
        # Изоляция здесь механизм: чужих ответов в пуле просто нет, и запрос по
        # чужому идентификатору ничего не найдёт — не потому, что запрещено, а
        # потому что нечего отдать.
        pool = [a for a in answers if owner(a) == str(persona_id)]

    wanted = args.get("persona_ids")
    if isinstance(wanted, list) and wanted:
        keep = {str(w) for w in wanted}
        pool = [a for a in pool if owner(a) in keep]

    cut, truncated, matched = _cut(pool, MAX_ANSWERS_PER_CALL)
    return {
        "answers": [copy.deepcopy(a) for a in cut],
        "truncated": truncated,
        "matched": matched,
    }


def dispatch(
    name: str,
    args: dict[str, Any],
    *,
    pack: dict[str, Any],
    answers: list[dict[str, Any]],
    persona_id: str | None = None,
) -> dict[str, Any]:
    """
    Исполняет вызов инструмента локально, по уже прочитанным данным.

    Никаких походов в Mongo отсюда: пакет и ответы читаются один раз при входе
    в разговор. Инструмент, ходящий в базу на каждый вызов, превратил бы пять
    раундов в пять чтений одного и того же.

    Неизвестное имя возвращает ОШИБКУ, а не пустоту. Модель вправе выдумать
    имя; пустой ответ она прочтёт как «данных нет» и сочинит по памяти, а
    названный отказ — как отказ.
    """
    if name == "get_scenes":
        return _get_scenes(args, pack)
    if name == "search_scenes":
        return _search_scenes(args, pack)
    if name == "get_transcript":
        return _get_transcript(args, pack)
    if name == "get_persona_answers":
        return _get_persona_answers(args, answers, persona_id)

    known = ", ".join(sorted(t["function"]["name"] for t in TOOL_SPECS))
    return {"error": f"инструмента {name} нет. Доступны: {known}"}
