"""
Модульные тесты Analytics-агента (#20).

CDD-тест задачи проверяет требование целиком. Здесь — кирпичи по отдельности:
формула NPS на границах, поведение агрегата на пустом и вырожденном входе,
распознавание опоры у утверждения. Граничные случаи в CDD-тест не помещаются, а
ломаются именно они.
"""

from __future__ import annotations

from agent_core.analytics.aggregate import (
    aggregate,
    retention_risk_points,
    surviving,
)
from agent_core.analytics.report import DISCLAIMER, build_report, has_support


def answer(persona="p0", *, replication=0, overall=7, nps=None, retention="скорее досмотреть",
           emotions=None, why="Обоснование персоны"):
    return {
        "persona_id": persona, "persona_name": persona, "replication": replication,
        "answer": {
            "scores": {"overall_impression": overall, "plot": overall, "acting": overall,
                       "music": overall, "cinematography": overall},
            "perception": {
                "emotions_evoked": ["интерес"] if emotions is None else emotions,
                "retention_intent": retention,
                "recommendation_nps_1_to_10": overall if nps is None else nps,
            },
            "verbatims": {"why_impression": why},
            "grounding_refs": ["00:10 сцена"],
        },
    }


# ─── NPS ─────────────────────────────────────────────────────────────────────


def test_nps_all_promoters():
    agg = aggregate([answer(f"p{i}", overall=10) for i in range(4)])
    assert agg["nps"] == 100.0


def test_nps_all_detractors():
    agg = aggregate([answer(f"p{i}", overall=3) for i in range(4)])
    assert agg["nps"] == -100.0


def test_nps_neutrals_do_not_count_either_way():
    """Семёрки и восьмёрки — нейтралы: в числитель не идут, знаменатель увеличивают."""
    answers = [answer("p0", overall=10), answer("p1", overall=7), answer("p2", overall=8)]
    assert aggregate(answers)["nps"] == round(100 / 3, 4)


def test_nps_boundary_nine_is_promoter_and_six_is_detractor():
    assert aggregate([answer("p0", overall=9)])["nps"] == 100.0
    assert aggregate([answer("p0", overall=6)])["nps"] == -100.0


# ─── Пустой и вырожденный вход ───────────────────────────────────────────────


def test_empty_input_gives_none_not_zero():
    """
    Ноль читается как измеренный результат, None — как отсутствие данных.

    Отчёт с NPS = 0 на пустой выборке выглядит как нейтральная аудитория, а не
    как отсутствие аудитории, и это ровно та ошибка, которую нельзя заметить.
    """
    agg = aggregate([])
    assert agg["nps"] is None
    assert agg["retention_rate"] is None
    assert agg["core_scores_mean"]["overall_impression"] is None
    assert agg["sample_size"] == 0


def test_unknown_retention_is_excluded_from_denominator():
    """«Затрудняюсь ответить» не считается ни за досмотр, ни против."""
    answers = [answer("p0", retention="скорее досмотреть"),
               answer("p1", retention="Затрудняюсь ответить")]
    assert aggregate(answers)["retention_rate"] == 100.0


# ─── Эмоции ──────────────────────────────────────────────────────────────────


def test_emotional_index_from_share_when_emotions_are_words():
    answers = [answer("p0", emotions=["интерес"]), answer("p1", emotions=[])]
    assert aggregate(answers)["emotional_index"] == 5.0


def test_emotional_index_uses_numbers_when_corpus_put_them_there():
    """В корпусе в emotions_evoked затесались подписи шкалы — известный дефект данных."""
    answers = [answer("p0", emotions=[8]), answer("p1", emotions=[6])]
    assert aggregate(answers)["emotional_index"] == 7.0


def test_numbers_do_not_become_emotions_in_top():
    answers = [answer("p0", emotions=[10]), answer("p1", emotions=["интерес"])]
    names = [e["name"] for e in aggregate(answers)["top_emotions"]]
    assert names == ["интерес"]


def test_emotion_repeated_within_one_answer_counts_once():
    answers = [answer("p0", emotions=["интерес", "Интерес", "интерес"])]
    top = aggregate(answers)["top_emotions"]
    assert top[0]["count"] == 1


# ─── QA-флаги ────────────────────────────────────────────────────────────────


def test_sample_level_flag_excludes_nothing():
    """Вердикт по выборке целиком (diversity) не адресует отдельный ответ."""
    flags = [{"kind": "diversity", "persona_id": None, "verdict": "regenerate"}]
    assert len(surviving([answer("p0"), answer("p1")], flags)) == 2


def test_ok_verdict_excludes_nothing():
    flags = [{"kind": "grounding", "persona_id": "p0", "replication": 0, "verdict": "ok"}]
    assert len(surviving([answer("p0")], flags)) == 1


def test_flag_matches_replication_not_only_persona():
    """У персоны с повторами бракуется конкретный повтор, а не все её ответы."""
    answers = [answer("p0", replication=0), answer("p0", replication=1)]
    flags = [{"persona_id": "p0", "replication": 1, "verdict": "regenerate"}]
    kept = surviving(answers, flags)
    assert [a["replication"] for a in kept] == [0]


# ─── Точки риска ─────────────────────────────────────────────────────────────


PACK = {"duration_sec": 600.0, "timeline": [{"start": 0.0, "end": 600.0, "scene": "кухня"}]}


def test_risk_point_only_from_those_who_would_stop():
    """
    Таймкод довольного зрителя — отсылка к понравившейся сцене.

    Считать её точкой риска значило бы получить риск ровно там, где сильнее
    всего зацепило.
    """
    answers = [
        answer("p0", retention="скорее досмотреть", why="Отличная сцена на 02:00"),
        answer("p1", retention="выключил бы", why="Бросил бы на 03:00"),
    ]
    points = retention_risk_points(answers, pack=PACK)
    assert [p["timestamp_sec"] for p in points] == [180.0]


def test_risk_point_counts_personas_not_mentions():
    answers = [
        answer("p0", retention="выключил бы", why="на 03:00 бросил, ещё раз 03:00"),
        answer("p1", retention="выключил бы", why="тоже на 03:00"),
    ]
    assert retention_risk_points(answers, pack=PACK)[0]["personas"] == 2


def test_risk_point_carries_scene_from_timeline():
    answers = [answer("p0", retention="выключил бы", why="Бросил на 03:00")]
    assert retention_risk_points(answers, pack=PACK)[0]["scene"] == "кухня"


# ─── Опора утверждения ───────────────────────────────────────────────────────


def test_statement_with_timecode_has_support():
    assert has_support("После 04:10 половина зрителей отваливается")


def test_statement_with_quote_has_support():
    assert has_support("Персона 4: «Бросил бы на середине, дальше не тянет»")


def test_bare_claim_has_no_support():
    assert not has_support("Аудитория в целом настроена положительно")


def test_short_quoted_fragment_is_not_support():
    """Кавычки вокруг двух слов — не цитата, а выделение; опорой они не считаются."""
    assert not has_support('Материал вызвал "интерес" у аудитории')


# ─── Отчёт ───────────────────────────────────────────────────────────────────


def test_report_always_carries_disclaimer():
    report = build_report(answers=[answer("p0")], pack=PACK, model=None)
    assert report["disclaimer"] == DISCLAIMER


def test_report_without_model_still_has_numbers():
    report = build_report(answers=[answer("p0", overall=8)], pack=PACK, model=None)
    assert report["aggregate"]["core_scores_mean"]["overall_impression"] == 8.0
    assert report["narrative"] == []
    assert any("нарратив" in d.lower() for d in report["degraded"])


def test_model_failure_does_not_lose_the_aggregate():
    """Отказ модели после оплаченных транскрипции и пятисот ответов не отменяет отчёт."""

    class Broken:
        def complete(self, *, system, user):
            raise RuntimeError("провайдер недоступен")

    report = build_report(answers=[answer("p0")], pack=PACK, model=Broken())
    assert report["aggregate"]["sample_size"] == 1
    assert any("провайдер недоступен" in d for d in report["degraded"])
