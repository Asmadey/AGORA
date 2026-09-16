"""
Что из пакета материала едет в модель, а что — мёртвый груз.

─── Что случилось ───────────────────────────────────────────────────────────
16.09.2026 чат по прогону 0091 отвечал отказом:

    This model's maximum context length is 262144 tokens. However, you
    requested 1200 output tokens and your prompt contains at least 260945
    input tokens.

Замер на боевом разобрал эти 260 945 по частям (оценка сошлась — 261 061):

    video_understanding (пакет)   230 551   88.3 %
      ├ scenes                    157 953
      ├ timeline                   61 403
      └ transcript                 11 087
    all_persona_answers            26 465   10.1 %
    report                          3 820    1.5 %

─── Мёртвый груз ────────────────────────────────────────────────────────────
`timeline` — не данные, а ВИД. Он собран для экрана из тех же `scenes` и
`transcript`, в другой форме. Модель получала описания всех 322 сцен дважды.

`screenshot` — ссылка на файл в S3. Текстовая модель картинок не видит: 15 233
токена подписанных URL, из которых не следует ничего.

`frame_times`, `panel_index`, `key` — внутренние координаты нарезки и склейки
панелей. Они нужны конвейеру, а не собеседнику.

`timestamp` («6.00») — строковый двойник `timestamp_sec` (6.0).

Итого 89 242 токена, 34 % контекста, не несущих ни одного факта, которого нет
рядом.

─── Чего трогать НЕЛЬЗЯ, и почему это стоит отдельного теста ────────────────
Поле `time` выглядит четвёртым написанием времени и подлежащим сокращению.
Оно им не является: в нём лежит `0:06–0:16`, то есть ровно формат `MM:SS`,
который промпт требует для ссылок, а `has_support` ищет регуляркой
`\\d{1,2}:[0-5]\\d`. Убрав его, мы бы оставили модели только числа вида 6.0 —
она писала бы «на 6-й секунде», опора не засчитывалась бы, и каждый ответ
получал бы пометку «без опоры на материал».

Отказа при этом не было бы. Чат продолжал бы работать и выглядел бы исправным.
"""
from __future__ import annotations

import copy
import json

from agent_core.chat.context import analyst_context, persona_context, slim_pack

#: Пакет той же формы, что на боевом: поля взяты из прогона 0091.
PACK = {
    "title": "Тест",
    "duration_sec": 2936.0,
    "form": "serial",
    "stitched": True,
    "stats": {"scenes_total": 2},
    "dropped_scenes": [],
    "timeline": [
        {"start": 0.0, "end": 6.0, "scene": "дубль описания", "mood": "x",
         "is_cut": True, "time": "0:00–0:06", "screenshot": "tenants/a/b.jpg",
         "lines": []},
    ],
    "transcript": [
        {"start": 67.4, "end": 72.4, "text": "Смотри внимательно.", "speaker": "SPEAKER_00"},
    ],
    "scenes": [
        {
            "time": "0:00–0:06",
            "timestamp": "0.00",
            "timestamp_sec": 0.0,
            "end_sec": 6.0,
            "is_cut": True,
            "key": True,
            "panel_index": 0,
            "frame_times": [7.3, 9.9, 12.5, 15.1],
            "screenshot": (
                "tenants/de15d1e3/runs/8c8f0cce/frames/000000000.jpg"
                "?X-Amz-Signature=" + "a" * 64
            ),
            "scene_description": "Сцена показывает разрушение объектов.",
            "characters": [],
            "actions": ["текст появляется"],
            "cinematography": {"camera": "статичный", "lighting": "яркий", "shot": "крупный"},
            "mood": "динамичный",
            "notable": "логотип",
            "on_screen_text": "МИРИ",
            "setting": "студия",
        },
    ],
}

SURVEY = [{"key": "overall", "label": "Общее впечатление"}]
ANSWERS = [{"persona_id": "p1", "answers": {"overall": 7}},
           {"persona_id": "p2", "answers": {"overall": 4}}]
REPORT = {"summary": "итог", "survey_asked": SURVEY}
PERSONA = {"id": "p1", "name": "Анна", "dna": {"age": 30}}


def _scene(pack):
    return pack["scenes"][0]


# ─── Мёртвый груз убран ─────────────────────────────────────────────────────


def test_вид_для_экрана_в_модель_не_едет():
    """`timeline` собран из scenes и transcript — это те же данные в другой форме."""
    assert "timeline" not in slim_pack(PACK)


def test_ссылка_на_кадр_убрана():
    """Текстовая модель картинок не видит: подписанный URL — чистый вес."""
    assert "screenshot" not in _scene(slim_pack(PACK))


def test_внутренние_координаты_нарезки_убраны():
    s = _scene(slim_pack(PACK))
    for field in ("frame_times", "panel_index", "key"):
        assert field not in s, f"{field} нужен конвейеру, а не собеседнику"


def test_строковый_двойник_времени_убран():
    s = _scene(slim_pack(PACK))
    assert "timestamp" not in s, "«6.00» — двойник timestamp_sec"


# ─── А это трогать нельзя ───────────────────────────────────────────────────


def test_человеческий_таймкод_остаётся():
    """
    Без `time` модель не сможет сослаться в формате, который засчитает опору.

    Проверяется не наличие ключа, а ФОРМАТ: той же регуляркой, которой
    `has_support` ищет таймкод. Ключ на месте с содержимым «6.0» прошёл бы
    проверку на наличие и провалил бы задачу.
    """
    from agent_core.analytics.report import has_support

    s = _scene(slim_pack(PACK))
    assert "time" in s, "человеческий таймкод обязателен для ссылок"
    assert has_support(str(s["time"])), (
        f"таймкод должен быть в формате MM:SS, а не {s['time']!r}"
    )


def test_содержательные_поля_сцены_целы():
    s = _scene(slim_pack(PACK))
    for field in ("scene_description", "actions", "characters", "cinematography",
                  "mood", "notable", "on_screen_text", "setting",
                  "timestamp_sec", "end_sec", "is_cut"):
        assert field in s, f"{field} — содержание, а не служебное поле"


def test_речь_и_заголовок_целы():
    p = slim_pack(PACK)
    assert p["transcript"] == PACK["transcript"]
    assert p["title"] == PACK["title"]
    assert p["duration_sec"] == PACK["duration_sec"]
    assert p["stats"] == PACK["stats"]


# ─── Срез не портит то, из чего собран ──────────────────────────────────────


def test_исходный_пакет_не_меняется():
    """
    `context.py` копирует всё, что кладёт в срез, и по той же причине: пакет
    читается один раз и используется дальше. Чистка на месте испортила бы его
    для всех остальных.
    """
    before = copy.deepcopy(PACK)
    slim_pack(PACK)
    assert PACK == before


# ─── Оба режима пользуются чисткой ──────────────────────────────────────────


def test_аналитик_получает_очищенный_пакет():
    ctx = analyst_context(report=REPORT, pack=PACK, survey=SURVEY,
                          answers=ANSWERS, qa_flags=[], history=[])
    assert "timeline" not in ctx["video_understanding"]
    assert "screenshot" not in ctx["video_understanding"]["scenes"][0]


def test_персона_получает_очищенный_пакет():
    ctx = persona_context(persona=PERSONA, pack=PACK, survey=SURVEY,
                          answers=ANSWERS, history=[])
    assert "timeline" not in ctx["video_understanding"]
    assert "screenshot" not in ctx["video_understanding"]["scenes"][0]


# ─── Выигрыш измерим ────────────────────────────────────────────────────────


def test_чистка_снимает_заметную_долю_веса():
    """
    Порог намеренно грубый: точная доля зависит от материала, а тест обязан
    ловить «чистку отключили», а не колебания. На боевом прогоне 0091 замер
    дал 34 %; здесь требуется хотя бы четверть.
    """
    def size(o):
        return len(json.dumps(o, ensure_ascii=False))

    было, стало = size(PACK), size(slim_pack(PACK))
    assert стало < было * 0.75, f"было {было}, стало {стало}"
