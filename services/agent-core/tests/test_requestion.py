"""
Переспрос забракованных персон (п. 33 списка владельца).

─── Что здесь строится ───────────────────────────────────────────────────────
До этого забракованный ответ просто выпадал из агрегата: персона не
переспрашивалась, деньги за ответ были потрачены, а отчёт вставал на остатке и
выглядел при этом нормальным отчётом. Golden-сет ловил это как «агрегат посчитан
по 3 ответам из 12», человек — никак.

Теперь при доле отбраковки выше трети забракованные персоны отвечают заново, и
новый ответ проходит QA ещё раз. Вторая отбраковка окончательна: без дна цикл
крутился бы, пока не кончатся деньги.

─── Главная опасность, ради которой написан третий тест ──────────────────────
Претензия судьи адресована ОТВЕТУ, а переспрашивать надо ПЕРСОНУ. Положить текст
претензии в промпт — самый очевидный способ, и он же самый вредный: «в вербатиме
сказано, что герой скупал чипы, а в материале речь об отказе от DJI» — это
готовый правильный ответ. Вторая попытка станет лучше первой не потому, что
персона подумала, а потому, что ей подсказали, и отчёт будет измерять качество
подсказки.

Поэтому персона получает подсказку ПО ВИДУ претензии, а не по её тексту:
«опирайся только на материал и бери таймкод готовым» вместо пересказа того, что
именно она напутала. Тест проверяет это буквально — ни одно слово претензии не
должно доехать до промпта.
"""

from __future__ import annotations

import json

from agent_core.respondent import requestion as r


class Recording:
    """Клиент, запоминающий промпты. Отвечает одним и тем же разумным ответом."""

    def __init__(self, answer: dict | None = None):
        self.prompts: list[str] = []
        self.answer = answer or {
            "scores": {"overall_impression": 7, "plot": 6, "acting": 6,
                       "music": 5, "cinematography": 6},
            "perception": {"retention_intent": "скорее досмотреть",
                           "watched_share_pct": 70,
                           "recommendation_nps_1_to_10": 7},
            "survey_answers": {},
            "verbatims": {"why_impression": "нормально"},
            "grounding_refs": ["0:10–0:20"],
        }

    def complete(self, *, system: str, user: str) -> str:
        self.prompts.append(system + "\n" + user)
        return json.dumps(self.answer, ensure_ascii=False)


def _answer(pid: str) -> dict:
    return {"persona_id": pid, "persona_name": pid, "replication": 0, "answer": {}}


def _verdict(pid: str, kind: str, reason: str) -> dict:
    return {
        "kind": kind, "persona_id": pid, "replication": 0,
        "verdict": "regenerate", "reasons": [reason], "source": "judge",
    }


def test_a_single_rejection_is_enough_to_ask_again():
    """
    Одна отбраковка из двенадцати — уже повод переспросить.

    Так было не всегда. До 19.08 порог стоял на трети (`REQUESTION_SHARE`), и на
    прогоне № 0050 переспрос не запустился: восемь ответов из двадцати семи —
    это 29,6 %, ниже порога. Владелец прочитал «забракованные персоны
    переспрашиваются» как «всегда», и это была моя формулировка, а не его
    невнимательность.

    Порог убран. Вместо него — потолок числа переспрашиваемых ответов, потому
    что защищаться надо не от единичной претензии, а от прогона, где забракованы
    почти все.
    """
    answers = [_answer(f"p{i}") for i in range(12)]
    flagged = [_verdict("p0", "grounding", "выдумал сцену")]

    assert r.needs_requestion(answers, flagged)


def test_nothing_flagged_means_nothing_to_ask():
    """Пустая отбраковка — не повод звать модель ни разу."""
    assert not r.needs_requestion([_answer("p0")], [])


def test_no_answers_means_nothing_to_ask():
    """Пустой прогон: переспрашивать некого, и делить на ноль негде."""
    assert not r.needs_requestion([], [_verdict("p0", "grounding", "…")])


def test_only_the_flagged_are_asked_again():
    """Переспрашиваются забракованные, а не вся аудитория."""
    answers = [_answer(f"p{i}") for i in range(9)]
    flagged = [_verdict(f"p{i}", "grounding", "выдумал сцену") for i in range(4)]

    assert r.needs_requestion(answers, flagged)
    assert r.personas_to_ask(flagged) == {("p0", 0), ("p1", 0), ("p2", 0), ("p3", 0)}


# ─── Потолок вместо порога ───────────────────────────────────────────────────
#
# Порог защищал бюджет, отказываясь переспрашивать при малой отбраковке, — и
# отказывался ровно там, где переспрос дёшев. Потолок защищает его с другой
# стороны: при полностью забракованном прогоне переспрос удваивает стоимость,
# и вот от этого польза от него уже не окупает.

def test_cap_limits_how_many_answers_are_asked_again():
    flagged = [_verdict(f"p{i}", "grounding", "…") for i in range(40)]
    limited = r.limit_to_cap(r.personas_to_ask(flagged), cap=15)
    assert len(limited) == 15


def test_cap_keeps_the_order_stable():
    """
    Отбор при исчерпанном потолке обязан быть воспроизводимым: два прогона на
    одних данных должны переспросить одних и тех же. Случайная выборка сделала
    бы расхождение отчётов необъяснимым.
    """
    flagged = [_verdict(f"p{i}", "grounding", "…") for i in range(40)]
    first = r.limit_to_cap(r.personas_to_ask(flagged), cap=15)
    second = r.limit_to_cap(r.personas_to_ask(flagged), cap=15)
    assert first == second


def test_cap_below_the_number_flagged_is_reported_not_hidden():
    """
    Исчерпанный потолок обязан быть виден: иначе отчёт молча стоит на остатке —
    ровно то, ради чего переспрос и заводился.
    """
    targets = r.personas_to_ask([_verdict(f"p{i}", "grounding", "…") for i in range(20)])
    assert r.cap_exhausted(targets, cap=15)
    assert not r.cap_exhausted(targets, cap=20)
    assert not r.cap_exhausted(targets, cap=50)


def test_zero_cap_disables_requestion_entirely():
    """
    Ноль — законная настройка «не переспрашивать». Она нужна тому, кто считает
    каждый вызов; отсутствие такой возможности заставило бы его выключать QA.
    """
    answers = [_answer(f"p{i}") for i in range(9)]
    flagged = [_verdict("p0", "grounding", "…")]
    assert not r.needs_requestion(answers, flagged, cap=0)


def test_the_complaint_text_never_reaches_the_prompt():
    """
    Главный тест раздела: персона не получает текст претензии.

    Претензия — это готовый правильный ответ. Дав его персоне, мы сделаем
    вторую попытку лучше первой подсказкой, а не рассуждением, и отчёт станет
    измерять качество подсказки.
    """
    complaint = (
        "В вербатиме 'memorable_elements' утверждается, что герой скупал чипы "
        "NVIDIA, а в материале (0:22–0:29) речь об отказе от партнёрства с DJI"
    )
    hint = r.hint_for({"grounding"})

    # Ни одного значимого слова претензии: сверяем по словам длиннее пяти букв,
    # чтобы «который» и «материале» не создавали ложных совпадений.
    leaked = [
        w for w in {t.strip(".,'()").lower() for t in complaint.split() if len(t) > 5}
        if w in hint.lower()
    ]
    assert not leaked, f"в подсказку утекли слова претензии: {leaked}"

    # Подсказка при этом не пустая: она объясняет, ЧТО делать иначе.
    assert len(hint) > 40
    assert "таймкод" in hint.lower() or "материал" in hint.lower()


def test_hint_matches_the_kind_of_complaint():
    """Разные виды претензий требуют разного действия, а не общего «постарайся»."""
    grounding = r.hint_for({"grounding"})
    consistency = r.hint_for({"consistency"})

    assert grounding != consistency
    assert r.hint_for(set()) == ""


def test_second_rejection_is_final():
    """
    Дно у цикла есть.

    Без него переспрос крутился бы, пока не кончатся деньги, и каждый круг
    выглядел бы осмысленной работой.
    """
    assert r.MAX_ROUNDS == 1


# ─── Стык с узлом: потолок из настроек и что видно в отчёте ──────────────────
#
# Модуль выше можно написать, покрыть тестами и не подключить — тогда узел
# продолжит считать по порогу, а настройка будет ручкой, которая ничего не
# крутит. Ровно этот дефект занял всю прошлую сессию.

def _node_state(cap=None, **extra):
    snapshot = {} if cap is None else {"requestionCap": cap}
    return {
        "task_id": "t", "tenant_id": "de15d1e3-e2f6-41c7-966d-91c186046066",
        "settings_snapshot": snapshot, "content_pack_compact": {}, "survey": {},
        **extra,
    }


def test_node_reads_the_cap_from_the_settings_snapshot(monkeypatch):
    from agent_core.pipeline import nodes

    seen: dict[str, object] = {}

    def fake_needs(answers, flagged, cap=r.DEFAULT_CAP):
        seen["cap"] = cap
        return False

    monkeypatch.setattr(r, "needs_requestion", fake_needs)

    nodes._requestion_flagged(
        _node_state(cap=4),  # type: ignore[arg-type]
        [_answer("p0")],
        _Outcome([_verdict("p0", "grounding", "…")]),
        [],
    )
    assert seen.get("cap") == 4, (
        f"узел зовёт переспрос с потолком {seen.get('cap')}, а в настройках 4: "
        f"настройка есть, а ограничения нет"
    )


class _Outcome:
    """Минимальный итог опроса: узлу от него нужны только вердикты QA."""

    def __init__(self, flagged):
        self.flagged = flagged
        self.answers = []
        self.failures = 0
        self.failure_reasons = []


def test_report_says_requestion_was_not_needed(monkeypatch):
    """
    Молчание — худший из трёх исходов: по экрану не отличить «переспроса не
    понадобилось» от «переспрос не работает». Владелец на прогоне № 0050
    прочитал молчание как второе, и был прав по факту, но не по причине.
    """
    from agent_core.pipeline import nodes

    degraded: list[str] = []
    answers, count = nodes._requestion_flagged(
        _node_state(), [_answer("p0")], _Outcome([]), degraded,
    )
    assert count == 0
    assert any("переспрос" in d.lower() for d in degraded) is False, (
        "на прогоне без отбраковки в отчёт попала строка про переспрос"
    )


def test_report_names_the_exhausted_cap(monkeypatch):
    """
    Потолок исчерпан — отчёт обязан назвать, сколько ответов остались
    забракованными. Иначе он снова стоит на остатке и молчит об этом.
    """
    from agent_core.pipeline import nodes

    monkeypatch.setattr(nodes, "_load_personas", lambda state: [])

    degraded: list[str] = []
    nodes._requestion_flagged(
        _node_state(cap=2),  # type: ignore[arg-type]
        [_answer(f"p{i}") for i in range(9)],
        _Outcome([_verdict(f"p{i}", "grounding", "…") for i in range(9)]),
        degraded,
    )
    joined = " ".join(degraded)
    assert "потолок" in joined.lower(), f"исчерпанный потолок не назван: {degraded}"


def test_requestion_count_reaches_the_report():
    """
    Число переспрошенных доезжает до сводки, которую читает экран.

    ─── Что ловится ──────────────────────────────────────────────────────────
    Переспрос заведён 19.08.2026 и работал. Число переспрошенных при этом
    оставалось в состоянии конвейера (`qa_requestioned`) и в отчёт не
    попадало — в него едет только `qa_summary`. Экран поэтому девять дней
    писал «перегенерации ответов в системе нет»: подпись была написана до
    механизма, а опровергнуть её было нечем — числа на экране не существовало.

    Дефект того же рода, что и потерянная анкета: механизм есть, провода нет,
    и отличить это от «механизма нет» по интерфейсу невозможно.
    """
    from agent_core.analytics.report import build_report

    summary = {"checked": 12, "flagged": 3, "escalated": 1,
               "judge_failures": 0, "by_kind": {}, "by_source": {},
               "requestioned": 8}

    report = build_report(answers=[], pack={}, qa_summary=summary)

    assert report["qa_summary"]["requestioned"] == 8, (
        "число переспрошенных не доехало до отчёта — экран снова не сможет "
        "сказать, что произошло с забракованными"
    )
    # «Исключено» — итог ПОСЛЕ переспроса: вердикты второго круга заменяют
    # вердикты первого. Пара «переспрошено 8, исключено 3» законна и означает,
    # что пять ответов вернулись годными.
    assert report["qa_summary"]["flagged"] == 3
