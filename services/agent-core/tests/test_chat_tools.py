"""
Инструменты чата: модель спрашивает материал, а не получает его целиком.

─── Почему чистки контекста мало ────────────────────────────────────────────
Этап 0 снял 34.7 % веса и увёл прогон 0091 с 261 103 токенов на 170 613. Это
лечит сегодняшний отказ и не лечит задачу: 48 минут дали 322 сцены, двухчасовой
фильм даст около восьмисот — одни только сцены займут ~307 000, и потолок
вернётся. Сто персон вместо сорока добавят ещё ~40 000.

Сокращать дальше нечем: всё, что осталось, — содержание.

─── Что вместо этого ────────────────────────────────────────────────────────
В контексте постоянно живёт ОГЛАВЛЕНИЕ: номер сцены, таймкод, одна фраза. Для
322 сцен это около 8 000 токенов вместо 158 000. Полные описания модель
запрашивает инструментом по номерам или по диапазону времени.

Проверено 16.09.2026, что шлюз это умеет: Cloud.ru с Qwen3.6 вернул
`finish_reason=tool_calls` и верно извлёк `{"from_sec": 60, "to_sec": 90}` из
вопроса «что происходит между 60 и 90 секундой».

─── Что здесь охраняется ────────────────────────────────────────────────────
**Нумерация одна на весь продукт.** Сцена 47 в оглавлении, сцена 47 на экране
исследования и сцена 47 в ответе модели — одна и та же сцена. Разошедшаяся
нумерация не даёт ошибки: она даёт уверенный ответ про чужую сцену.

**Обрезка всегда названа.** Инструмент с потолком, молча отдающий часть, хуже
инструмента без потолка: модель считает ответ полным и говорит «таких сцен
всего три», когда их пятьдесят семь.

**Изоляция персоны — механизм, а не правило.** В режиме допроса инструменту
нечего вернуть про чужие ответы, как и в `persona_context`. Проверка вывода
зелена ровно до первого совпадения формулировок.
"""
from __future__ import annotations

import json

from agent_core.chat.tools import (
    MAX_SCENES_PER_CALL,
    TOOL_SPECS,
    dispatch,
    scene_index,
)


def _scene(n: int, desc: str, start: float, end: float, **extra):
    m, s = divmod(int(start), 60)
    me, se = divmod(int(end), 60)
    return {
        "time": f"{m}:{s:02d}–{me}:{se:02d}",
        "timestamp_sec": start,
        "end_sec": end,
        "scene_description": desc,
        "mood": "нейтральное",
        "actions": [f"действие {n}"],
        "characters": [],
        "cinematography": {"camera": "статичный"},
        "is_cut": True,
        **extra,
    }


PACK = {
    "title": "Тест",
    "duration_sec": 300.0,
    "scenes": [
        _scene(1, "Разрушение объектов на ярком фоне", 0, 6),
        _scene(2, "Титровый ролик с логотипом НТВ", 6, 16),
        _scene(3, "Женщина в ретро-одежде в тёмном коридоре", 16, 40),
        _scene(4, "Разговор двух героев на кухне", 60, 95),
        _scene(5, "Погоня по ночному городу", 95, 140),
    ],
    "transcript": [
        {"start": 67.4, "end": 72.4, "text": "Смотри внимательно.", "speaker": "SPEAKER_00"},
        {"start": 73.0, "end": 78.0, "text": "Я не хочу этого делать.", "speaker": "SPEAKER_01"},
        {"start": 200.0, "end": 204.0, "text": "Поздно бежать.", "speaker": "SPEAKER_00"},
    ],
}

ANSWERS = [
    {"persona_id": "p1", "persona_name": "Анна", "answers": {"overall": 7},
     "comment": "Понравился визуал, но сюжет затянут"},
    {"persona_id": "p2", "persona_name": "Борис", "answers": {"overall": 3},
     "comment": "Слишком мрачно, бросил бы на середине"},
    {"persona_id": "p3", "persona_name": "Вера", "answers": {"overall": 9},
     "comment": "Отличная погоня, смотрела не отрываясь"},
]


# ─── Оглавление ─────────────────────────────────────────────────────────────


def test_оглавление_нумерует_с_единицы_и_подряд():
    idx = scene_index(PACK)
    assert [s["n"] for s in idx] == [1, 2, 3, 4, 5]


def test_нумерация_совпадает_с_экраном():
    """
    Экран нумерует сцены по порядку в `pack["scenes"]`, начиная с единицы
    (`Timeline.tsx`, `sceneNumber`). Оглавление обязано давать те же номера:
    сцена 47 в ответе модели и сцена 47 на экране — одна сцена.
    """
    idx = scene_index(PACK)
    for n, scene in enumerate(PACK["scenes"], start=1):
        entry = next(e for e in idx if e["n"] == n)
        assert entry["time"] == scene["time"]


def test_оглавление_несёт_таймкод_годный_для_ссылки():
    from agent_core.analytics.report import has_support

    for e in scene_index(PACK):
        assert has_support(e["time"]), f"таймкод {e['time']!r} не засчитается как опора"


def test_оглавление_много_легче_полного_описания():
    полное = len(json.dumps(PACK["scenes"], ensure_ascii=False))
    оглавление = len(json.dumps(scene_index(PACK), ensure_ascii=False))
    assert оглавление < полное / 2, f"{оглавление} против {полное}"


# ─── Объявления инструментов ────────────────────────────────────────────────


def test_объявлены_инструменты_для_сцен_речи_и_ответов():
    names = {t["function"]["name"] for t in TOOL_SPECS}
    assert {"get_scenes", "search_scenes", "get_transcript", "get_persona_answers"} <= names


def test_объявления_годны_для_шлюза():
    """Форма та же, что приняла Cloud.ru при проверке 16.09.2026."""
    for t in TOOL_SPECS:
        assert t["type"] == "function"
        f = t["function"]
        assert f["name"] and f["description"]
        assert f["parameters"]["type"] == "object"
        assert isinstance(f["parameters"]["properties"], dict)


# ─── get_scenes ─────────────────────────────────────────────────────────────


def test_сцены_по_номерам():
    r = dispatch("get_scenes", {"numbers": [2, 4]}, pack=PACK, answers=ANSWERS)
    assert [s["n"] for s in r["scenes"]] == [2, 4]
    assert "НТВ" in r["scenes"][0]["scene_description"]


def test_сцены_по_диапазону_времени():
    r = dispatch("get_scenes", {"from_sec": 60, "to_sec": 90}, pack=PACK, answers=ANSWERS)
    # Сцена 4 идёт 60–95: она пересекает запрошенный отрезок.
    assert [s["n"] for s in r["scenes"]] == [4]


def test_несуществующий_номер_назван_а_не_проглочен():
    r = dispatch("get_scenes", {"numbers": [2, 99]}, pack=PACK, answers=ANSWERS)
    assert [s["n"] for s in r["scenes"]] == [2]
    assert 99 in r["not_found"], "промах по номеру обязан быть назван"


def test_обрезка_по_потолку_названа():
    big = {"scenes": [_scene(i, f"сцена {i}", i * 10, i * 10 + 9)
                      for i in range(1, MAX_SCENES_PER_CALL + 8)]}
    r = dispatch("get_scenes", {"from_sec": 0, "to_sec": 100000},
                 pack=big, answers=[])
    assert len(r["scenes"]) == MAX_SCENES_PER_CALL
    assert r["truncated"] is True
    assert r["matched"] == MAX_SCENES_PER_CALL + 7, "сказано, сколько нашлось всего"


def test_без_обрезки_признак_не_поднят():
    r = dispatch("get_scenes", {"numbers": [1]}, pack=PACK, answers=ANSWERS)
    assert r["truncated"] is False


# ─── search_scenes ──────────────────────────────────────────────────────────


def test_поиск_по_словам_находит_сцену():
    r = dispatch("search_scenes", {"query": "погоня"}, pack=PACK, answers=ANSWERS)
    assert [s["n"] for s in r["scenes"]] == [5]


def test_поиск_не_зависит_от_регистра():
    r = dispatch("search_scenes", {"query": "НТВ"}, pack=PACK, answers=ANSWERS)
    assert 2 in [s["n"] for s in r["scenes"]]
    r2 = dispatch("search_scenes", {"query": "нтв"}, pack=PACK, answers=ANSWERS)
    assert [s["n"] for s in r["scenes"]] == [s["n"] for s in r2["scenes"]]


def test_пустой_поиск_возвращает_пусто_а_не_всё():
    """Пустой запрос — это «не знаю, что искать», а не «дай всё»."""
    r = dispatch("search_scenes", {"query": "   "}, pack=PACK, answers=ANSWERS)
    assert r["scenes"] == []


# ─── get_transcript ─────────────────────────────────────────────────────────


def test_речь_по_отрезку():
    r = dispatch("get_transcript", {"from_sec": 60, "to_sec": 80}, pack=PACK, answers=ANSWERS)
    texts = [line["text"] for line in r["lines"]]
    assert "Смотри внимательно." in texts
    assert "Поздно бежать." not in texts


# ─── get_persona_answers ────────────────────────────────────────────────────


def test_ответы_персон_отдаются_аналитику():
    r = dispatch("get_persona_answers", {}, pack=PACK, answers=ANSWERS)
    assert len(r["answers"]) == 3


def test_ответы_можно_взять_по_идентификатору():
    r = dispatch("get_persona_answers", {"persona_ids": ["p2"]}, pack=PACK, answers=ANSWERS)
    assert [a["persona_id"] for a in r["answers"]] == ["p2"]


def test_персоне_недоступны_чужие_ответы():
    """
    Изоляция — механизм, а не правило: в режиме допроса инструменту нечего
    вернуть про чужих, даже если модель прямо их запросит по идентификатору.
    """
    r = dispatch("get_persona_answers", {"persona_ids": ["p1", "p2", "p3"]},
                 pack=PACK, answers=ANSWERS, persona_id="p1")
    assert [a["persona_id"] for a in r["answers"]] == ["p1"]

    r2 = dispatch("get_persona_answers", {}, pack=PACK, answers=ANSWERS, persona_id="p1")
    assert [a["persona_id"] for a in r2["answers"]] == ["p1"]


# ─── Неизвестный инструмент ─────────────────────────────────────────────────


def test_неизвестный_инструмент_не_молчит():
    """
    Модель вправе выдумать имя. Пустой ответ она прочтёт как «данных нет» и
    сочинит по памяти; отказ с именем она прочтёт как отказ.
    """
    r = dispatch("get_everything", {}, pack=PACK, answers=ANSWERS)
    assert "error" in r
    assert "get_everything" in r["error"]


def test_каждый_объявленный_инструмент_исполняется():
    """Объявление без исполнения — обещание, которого никто не сдержит."""
    for spec in TOOL_SPECS:
        name = spec["function"]["name"]
        r = dispatch(name, {}, pack=PACK, answers=ANSWERS)
        assert "error" not in r, f"{name} объявлен, но не исполняется"
