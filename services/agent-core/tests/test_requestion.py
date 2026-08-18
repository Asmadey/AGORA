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


def test_below_threshold_nobody_is_asked_again():
    """
    Одна отбраковка из двенадцати — не повод переспрашивать всех.

    Переспрос стоит денег: каждая попытка это вызов модели с полным пакетом
    материала. Порог существует затем, чтобы платить за него только когда
    отчёт действительно под угрозой, а не при каждой единичной претензии.
    """
    answers = [_answer(f"p{i}") for i in range(12)]
    flagged = [_verdict("p0", "grounding", "выдумал сцену")]

    assert not r.needs_requestion(answers, flagged)


def test_above_threshold_only_the_flagged_are_asked_again():
    """Переспрашиваются забракованные, а не вся аудитория."""
    answers = [_answer(f"p{i}") for i in range(9)]
    flagged = [_verdict(f"p{i}", "grounding", "выдумал сцену") for i in range(4)]

    assert r.needs_requestion(answers, flagged)
    assert r.personas_to_ask(flagged) == {("p0", 0), ("p1", 0), ("p2", 0), ("p3", 0)}


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
