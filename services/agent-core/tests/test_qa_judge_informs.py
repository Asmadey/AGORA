"""
Из агрегата выпадают только объективные нарушения правил, не вердикты судьи.

─── Решение владельца 17.09.2026 ─────────────────────────────────────────────
«Задача QA-агента не блокировать появление ответов, а информировать меня как
контролёра, где они ошибаются».

На уровне ПЕРСОН так и было: забракованная остаётся в наборе с пометкой и
отвечает (`test_failed_persona_stays_in_the_set`). На уровне ОТВЕТОВ был сделан
обратный выбор, и цена его измерена на боевом:

    прогон 1:  в агрегате 15 ответов, исключено QA 25   (из 40, то есть 62 %)
    прогон 2:  в агрегате 13,          исключено QA  7

Отчёт строился на 38 % ответов.

─── Почему не «считать всё подряд» ──────────────────────────────────────────
QA ответов состоит из двух разных вещей. Детерминированные правила
(`qa/checks.py`) ловят объективный брак: балл вне шкалы 1–10, таймкод за
пределами длительности ролика, пустые вербатимы, незакрытые вопросы анкеты.
Балл 15 по десятибалльной шкале в среднее не положишь — такой ответ нельзя
агрегировать, и дело тут не в мнении.

LLM-судья ловит субъективное, и ошибается: коммит `0ba9e30` — «Проход 35: три
четверти отбраковок QA оказались дефектом правила, а не качеством». Сегодняшние
замеры это продолжают — судья писал «в тексте не указано, но и не противоречит»
и всё равно ставил `consistent: false`.

Отсюда граница: **правила гейтят, судья информирует.** Флаг судьи остаётся на
карточке ответа и виден человеку, но ответ участвует в агрегате.

─── Про `escalated` ─────────────────────────────────────────────────────────
Эскалация — тот же вердикт судьи, перепроверенный моделью побольше. Он
субъективен ровно так же, поэтому тоже информирует, а не гейтит. Гейтит только
`source == "rule"`.
"""

from __future__ import annotations

from agent_core.analytics.aggregate import surviving

BASE = {"persona_id": "p1", "replication": 0, "verdict": "regenerate"}


def answer(pid: str, rep: int = 0) -> dict:
    return {"persona_id": pid, "replication": rep, "scores": {"overall_impression": 7}}


def flag(pid: str, source: str, kind: str = "consistency", **extra) -> dict:
    return {
        "persona_id": pid, "replication": 0, "verdict": "regenerate",
        "kind": kind, "source": source, "confidence": 1.0, "reasons": ["…"],
        **extra,
    }


def test_rule_violation_still_drops_the_answer():
    """Объективный брак не агрегируется: балл вне шкалы в среднее не положишь."""
    answers = [answer("p1"), answer("p2")]
    kept = surviving(answers, [flag("p1", source="rule")])
    assert [a["persona_id"] for a in kept] == ["p2"]


def test_judge_verdict_keeps_the_answer():
    """Вердикт судьи помечает карточку и НЕ выбрасывает ответ из агрегата."""
    answers = [answer("p1"), answer("p2")]
    kept = surviving(answers, [flag("p1", source="judge")])
    assert [a["persona_id"] for a in kept] == ["p1", "p2"], (
        "ответ выпал по субъективному вердикту — это и есть блокировка, "
        "от которой владелец отказался"
    )


def test_escalated_verdict_keeps_the_answer():
    """
    Эскалация — тот же судья, только модель побольше.

    Субъективность от размера модели не исчезает.
    """
    answers = [answer("p1")]
    kept = surviving(answers, [flag("p1", source="escalated", escalated=True)])
    assert len(kept) == 1


def test_rule_wins_over_judge_on_the_same_answer():
    """Смешанные флаги: одного правила достаточно, чтобы исключить."""
    answers = [answer("p1")]
    kept = surviving(answers, [flag("p1", source="judge"), flag("p1", source="rule")])
    assert kept == []


def test_flag_without_source_is_treated_as_a_rule():
    """
    Старые артефакты без поля `source`.

    Отчёты, снятые до появления поля, его не содержат. Считать их вердиктами
    судьи значило бы задним числом вернуть в агрегаты ответы, которых там не
    было, — и прежние отчёты стали бы пересчитываться иначе. Поэтому умолчание
    консервативное: ведём себя как раньше.
    """
    answers = [answer("p1")]
    kept = surviving(answers, [{**BASE, "kind": "consistency"}])
    assert kept == []


def test_ok_verdict_never_drops():
    answers = [answer("p1")]
    kept = surviving(answers, [{**flag("p1", source="rule"), "verdict": "ok"}])
    assert len(kept) == 1


def test_sample_wide_verdict_drops_nothing():
    """У diversity нет адресата: `persona_id` пуст."""
    answers = [answer("p1"), answer("p2")]
    flags = [{"persona_id": None, "verdict": "regenerate", "kind": "diversity", "source": "rule"}]
    assert len(surviving(answers, flags)) == 2
