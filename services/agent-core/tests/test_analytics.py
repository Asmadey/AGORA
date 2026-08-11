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


# ─── Посегментный срез ───────────────────────────────────────────────────────


def seg_answer(persona, *, age_group, geo, gender, replication=0, overall=7):
    """Ответ с записанным срезом DNA — так его кладёт respondent/run.py."""
    a = answer(persona, replication=replication, overall=overall)
    a["segment"] = {"age_group": age_group, "geo": geo, "gender": gender}
    return a


def cohort(n, *, age_group="25-34", geo="столицы", gender="жен", overall=7, prefix="p"):
    return [
        seg_answer(f"{prefix}{i}", age_group=age_group, geo=geo, gender=gender,
                   overall=overall)
        for i in range(n)
    ]


def test_no_segment_data_gives_none_not_empty_dict():
    """
    «Срез не считали» и «посчитали, групп нет» — разные факты.

    Пустой словарь на экране выглядит как аудитория без сегментов, то есть как
    результат. None говорит, что данных для среза в прогоне не было.
    """
    agg = aggregate([answer("p0")])
    assert agg["segment_breakdown"] is None


def test_breakdown_splits_by_each_dimension():
    answers = (
        cohort(6, age_group="18-24", overall=9, prefix="young")
        + cohort(6, age_group="45-59", overall=4, prefix="old")
    )
    by_age = aggregate(answers)["segment_breakdown"]["age_group"]
    assert by_age["18-24"]["core_scores_mean"]["overall_impression"] == 9.0
    assert by_age["45-59"]["core_scores_mean"]["overall_impression"] == 4.0
    assert by_age["18-24"]["personas"] == 6


def test_small_segment_is_suppressed_not_shown():
    """Средняя по трём персонам — шум, который на экране неотличим от факта."""
    answers = cohort(6, geo="столицы", prefix="a") + cohort(3, geo="иные НП", prefix="b")
    by_geo = aggregate(answers)["segment_breakdown"]["geo"]
    assert "столицы" in by_geo
    assert "иные НП" not in by_geo


def test_suppressed_segment_is_reported_not_silently_dropped():
    """Молча пропавшая группа читается как потерянные данные."""
    answers = cohort(6, geo="столицы", prefix="a") + cohort(3, geo="иные НП", prefix="b")
    suppressed = aggregate(answers)["segment_breakdown"]["suppressed"]
    assert {"dimension": "geo", "value": "иные НП", "personas": 3} in suppressed


def test_threshold_counts_personas_not_answers():
    """
    Порог по персонам, а не по ответам.

    Две персоны при перекрытии ×3 дают шесть ответов. Считать их шестью
    наблюдениями — это выдать удвоенную уверенность за расширенную выборку:
    повтор одной персоны не независим от неё самой.
    """
    answers = [
        seg_answer(f"p{i}", age_group="60+", geo="столицы", gender="жен", replication=r)
        for i in range(2) for r in range(3)
    ]
    breakdown = aggregate(answers, replication_count=3)["segment_breakdown"]
    assert "60+" not in breakdown["age_group"]
    assert any(s["value"] == "60+" and s["personas"] == 2
               for s in breakdown["suppressed"])


def test_qa_flagged_answers_leave_the_segment_too():
    """Иначе сегмент считался бы по ответам, которые отчёт сам забраковал."""
    answers = cohort(6, age_group="18-24", overall=9, prefix="y")
    answers.append(seg_answer("bad", age_group="18-24", geo="столицы",
                              gender="жен", overall=1))
    flags = [{"persona_id": "bad", "replication": 0, "verdict": "regenerate"}]
    by_age = aggregate(answers, qa_flags=flags)["segment_breakdown"]["age_group"]
    assert by_age["18-24"]["core_scores_mean"]["overall_impression"] == 9.0
    assert by_age["18-24"]["personas"] == 6


def test_partial_segment_does_not_break_other_dimensions():
    """Ответ без geo не должен обнулять разрез по возрасту."""
    answers = cohort(6, age_group="18-24", prefix="y")
    for a in answers[:2]:
        a["segment"].pop("geo")
    breakdown = aggregate(answers)["segment_breakdown"]
    assert breakdown["age_group"]["18-24"]["personas"] == 6
    assert "столицы" not in breakdown["geo"]


# ─── Разброс между повторами на уровне критерия ──────────────────────────────


def test_no_replication_gives_no_bounds():
    """При одном прогоне разбрасываться нечему, и пустая полоса на шкале врёт."""
    agg = aggregate([answer("p0")], replication_count=1)
    assert agg["replication_bounds"] == {}


def test_bounds_describe_one_persona_spread_not_the_crowd():
    """
    Полоса на шкале подписана «разброс между повторами», и она обязана мерить
    именно это. Разброс между персонами — другая величина: две согласные между
    собой персоны с разными оценками дали бы широкую полосу там, где ни одна
    персона сама себе не противоречила.
    """
    answers = [
        # p0 стабильна: 7,7,7. p1 скачет: 4,10 — среднее то же, разброс разный.
        answer("p0", replication=0, overall=7),
        answer("p0", replication=1, overall=7),
        answer("p1", replication=0, overall=4),
        answer("p1", replication=1, overall=10),
    ]
    bounds = aggregate(answers, replication_count=2)["replication_bounds"]
    overall = bounds["overall_impression"]
    # Средние границы по персонам: min (7+4)/2 = 5.5, max (7+10)/2 = 8.5.
    assert overall["min"] == 5.5
    assert overall["max"] == 8.5
    assert overall["mean"] == 7.0


def test_single_replication_persona_does_not_widen_the_band():
    """Персона с одним ответом разброса не имеет — её нельзя считать нулевым."""
    answers = [
        answer("p0", replication=0, overall=4),
        answer("p0", replication=1, overall=10),
        answer("p1", replication=0, overall=7),
    ]
    bounds = aggregate(answers, replication_count=2)["replication_bounds"]
    assert bounds["overall_impression"]["min"] == 4.0
    assert bounds["overall_impression"]["max"] == 10.0


# ─── Доля просмотра ──────────────────────────────────────────────────────────


def watched(persona, pct):
    a = answer(persona)
    a["answer"]["perception"]["watched_share_pct"] = pct
    return a


def test_watched_share_absent_gives_none_not_zero():
    """
    «Не спрашивали» и «не смотрели» на экране выглядят одинаково, если оба ноль.

    Поле необязательное: анкету без вопроса о доле просмотра пользователь вправе
    запустить, и отчёт по ней обязан честно показать прочерк.
    """
    assert aggregate([answer("p0")])["watched_share_mean"] is None


def test_watched_share_is_averaged():
    agg = aggregate([watched("p0", 100), watched("p1", 50)])
    assert agg["watched_share_mean"] == 75.0


def test_watched_share_outside_scale_is_dropped():
    """
    Шкала 0–100. Значение вне её — не «очень досмотрел», а испорченный ответ:
    модель отдала долю единицей либо промахнулась мимо формата. Втянув 1.0 в
    среднее, отчёт занизил бы досмотр на порядок и выглядел бы правдоподобно.
    """
    agg = aggregate([watched("p0", 80), watched("p1", 140), watched("p2", -5)])
    assert agg["watched_share_mean"] == 80.0


def test_watched_share_ignores_non_numeric():
    agg = aggregate([watched("p0", 80), watched("p1", "почти всё")])
    assert agg["watched_share_mean"] == 80.0


def test_watched_share_zero_is_a_real_answer():
    """Ноль — «не смотрел вообще», это ответ, а не отсутствие ответа."""
    assert aggregate([watched("p0", 0), watched("p1", 100)])["watched_share_mean"] == 50.0


def test_watched_share_respects_qa_exclusion():
    flags = [{"persona_id": "bad", "replication": 0, "verdict": "regenerate"}]
    agg = aggregate([watched("p0", 90), watched("bad", 10)], qa_flags=flags)
    assert agg["watched_share_mean"] == 90.0


# ─── Персоны как запасной источник среза ─────────────────────────────────────


def persona_row(pid, *, age_group="25-34", geo="столицы", gender="жен"):
    return {"id": pid, "dna": {"demographics": {
        "age_group": age_group, "geo": geo, "gender": gender, "age": 30}}}


def test_personas_fill_the_segment_when_the_card_has_none():
    """
    Прогоны, сохранённые до появления среза в карточке, разрез всё же получают —
    если состав аудитории передан явно.
    """
    answers = [answer(f"p{i}") for i in range(6)]
    personas = [persona_row(f"p{i}", age_group="18-24") for i in range(6)]
    by_age = aggregate(answers, personas=personas)["segment_breakdown"]["age_group"]
    assert by_age["18-24"]["personas"] == 6


def test_card_segment_wins_over_the_persona():
    """
    Карточка главнее реестра. Персону могли отредактировать после прогона, и
    тогда реестр описывает не ту аудиторию, на которой отчёт посчитан. Молча
    подменить срез значило бы задним числом переписать результат исследования.
    """
    answers = cohort(6, age_group="18-24", prefix="y")
    personas = [persona_row(f"y{i}", age_group="60+") for i in range(6)]
    by_age = aggregate(answers, personas=personas)["segment_breakdown"]["age_group"]
    assert "18-24" in by_age
    assert "60+" not in by_age


def test_personas_absent_from_the_run_are_ignored():
    """Реестр шире прогона: в нём персоны, которых в этом исследовании не было."""
    answers = [answer(f"p{i}") for i in range(6)]
    personas = [persona_row(f"p{i}") for i in range(50)]
    breakdown = aggregate(answers, personas=personas)["segment_breakdown"]
    assert breakdown["geo"]["столицы"]["personas"] == 6


def test_no_personas_and_no_segment_still_gives_none():
    assert aggregate([answer("p0")], personas=[])["segment_breakdown"] is None
