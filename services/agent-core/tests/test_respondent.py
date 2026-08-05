"""
Тесты respondent-агентов (#18): изоляция среза и расчёт разнообразия.

Метрики distinct-2 и дисперсии баллов подключены в evals/check.py как гейт
проекта, поэтому их поведение на краевых входах — не деталь реализации, а часть
контракта: метрика, которая зеленеет на пустом прогоне, хуже отсутствующей.
"""

from __future__ import annotations

import copy
import json

from agent_core.respondent.diversity import (
    DISTINCT2_MIN,
    SCORE_STDEV_MIN,
    distinct_2,
    diversity_report,
    score_stdev,
)
from agent_core.respondent.run import BATCH_SIZE, build_slice, parse_answer, run_survey

SYSTEM_TPL = (
    "Ты — {{persona_dna}}. Сегмент {{segment}}. "
    "Голос: {{verbatim_examples}}. {{score_priors}}"
)
USER_TPL = (
    "Материал: {{video_understanding}}\n"
    "Анкета: {{survey_questions}}\nНазвание: {{content_title}}"
)

PACK = {"title": "Ролик", "scenes": [{"timestamp_sec": 0.0, "scene_description": "Спор"}]}
SURVEY = {"questions": [{"id": "q1", "type": "scale", "text": "Оценка?"}]}

ANSWER = {
    "scores": {"overall_impression": 7},
    "verbatims": {"why_impression": "Живой спор зацепил", "memorable_elements": "Посуда"},
}


def persona(idx: int, secret: str | None = None) -> dict:
    return {
        "id": f"p{idx}", "name": f"Персона {idx}",
        "dna": {
            "demographics": {"age_group": "25-34", "age": 30},
            "narrative": secret or f"портрет {idx}",
        },
    }


class Recorder:
    def __init__(self, payload=None):
        self.sent: list[tuple[str, str]] = []
        self.payload = payload or ANSWER

    def complete(self, *, system: str, user: str) -> str:
        self.sent.append((system, user))
        return json.dumps(self.payload, ensure_ascii=False)


def run(**kw):
    base = dict(personas=[persona(0), persona(1)], pack=PACK, survey=SURVEY,
                client=Recorder(), replication_count=1, artifact_path=None,
                system_template=SYSTEM_TPL, user_template=USER_TPL)
    base.update(kw)
    return run_survey(**base)


# ─── Изоляция ────────────────────────────────────────────────────────────────


def test_slice_contains_only_own_dna():
    system, user = build_slice(
        persona(0, "СЕКРЕТ-A"), PACK, SURVEY,
        system_template=SYSTEM_TPL, user_template=USER_TPL,
    )
    assert "СЕКРЕТ-A" in system
    assert "Персона 1" not in system + user


def test_no_leak_across_many_personas_and_replications():
    """Утечка проявляется не на второй персоне, а на двадцатой во втором повторе."""
    people = [persona(0, "МАРКЕР-XYZ")] + [persona(i) for i in range(1, 20)]
    client = Recorder()
    outcome = run(personas=people, client=client, replication_count=3)

    for i, (system, user) in enumerate(client.sent):
        own = outcome.answers[i]["persona_id"] if i < len(outcome.answers) else None
        if own == "p0":
            continue
        assert "МАРКЕР-XYZ" not in system + user, f"утечка в промпте {i}"


def test_input_personas_not_mutated():
    people = [persona(0), persona(1)]
    before = copy.deepcopy(people)
    run(personas=people)
    assert people == before


def test_build_slice_is_pure():
    """Дважды собранный срез одной персоны совпадает: состояния между вызовами нет."""
    p = persona(0)
    a = build_slice(p, PACK, SURVEY, system_template=SYSTEM_TPL, user_template=USER_TPL)
    build_slice(persona(1), PACK, SURVEY, system_template=SYSTEM_TPL, user_template=USER_TPL)
    b = build_slice(p, PACK, SURVEY, system_template=SYSTEM_TPL, user_template=USER_TPL)
    assert a == b


# ─── Прогон ──────────────────────────────────────────────────────────────────


def test_replication_multiplies_answers():
    outcome = run(replication_count=3)
    assert len(outcome.answers) == 6
    assert {a["replication"] for a in outcome.answers} == {0, 1, 2}


def test_batch_size_is_contract():
    assert BATCH_SIZE == 5


def test_failure_does_not_abort_run():
    class Flaky(Recorder):
        def complete(self, *, system, user):
            if len(self.sent) == 0:
                self.sent.append((system, user))
                raise RuntimeError("таймаут")
            return super().complete(system=system, user=user)

    outcome = run(client=Flaky())
    assert len(outcome.answers) == 1
    assert outcome.failures == 1
    assert "таймаут" in outcome.failure_reasons[0]


def test_unparseable_answer_counts_as_failure():
    class Garbage(Recorder):
        def complete(self, *, system, user):
            self.sent.append((system, user))
            return "не JSON вовсе"

    outcome = run(client=Garbage())
    assert outcome.answers == []
    assert outcome.failures == 2


def test_artifact_written(tmp_path):
    path = tmp_path / "answers.json"
    run(artifact_path=path)
    data = json.loads(path.read_text("utf-8"))
    assert len(data["answers"]) == 2
    assert "diversity" in data


def test_fenced_json_is_parsed():
    """Модель штатно оборачивает JSON в ```json — терять на этом ответ нельзя."""
    assert parse_answer('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_answer('{"a": 1}') == {"a": 1}


# ─── Разнообразие ────────────────────────────────────────────────────────────


def test_distinct_2_empty_is_zero():
    """Пустой вход — это «нет разнообразия», а не «идеальное разнообразие».

    Иначе метрика зеленеет на прогоне, где не ответил никто.
    """
    assert distinct_2([]) == 0.0
    assert distinct_2(["", ""]) == 0.0


def test_distinct_2_identical_texts_low():
    assert distinct_2(["одна и та же фраза целиком"] * 10) < DISTINCT2_MIN


def test_distinct_2_varied_texts_high():
    texts = [
        "спор на кухне вышел живым и убедительным",
        "картинка красивая, но сюжет провисает",
        "герой раздражает, музыка спасает положение",
        "не мой жанр, выключил бы через десять минут",
    ]
    assert distinct_2(texts) >= DISTINCT2_MIN


def test_distinct_2_ignores_punctuation():
    """Точка в конце не должна порождать уникальную биграмму на каждом ответе."""
    with_dots = distinct_2(["слово другое слово."] * 5)
    without = distinct_2(["слово другое слово"] * 5)
    assert abs(with_dots - without) < 1e-9


def test_score_stdev_needs_two_values():
    assert score_stdev([{"overall_impression": 7}]) == 0.0
    assert score_stdev([]) == 0.0


def test_score_stdev_ignores_non_numeric():
    assert score_stdev([{"overall_impression": "семь"}, {"overall_impression": 7}]) == 0.0


def test_score_stdev_ignores_bool():
    """True == 1 в Python: без явной защиты булево значение сойдёт за балл."""
    assert score_stdev([{"overall_impression": True}, {"overall_impression": 7}]) == 0.0


def test_diversity_report_flags_collapse():
    same = [{"answer": {"scores": {"overall_impression": 7},
                        "verbatims": {"a": "одинаковый ответ у всех"}}} for _ in range(5)]
    rep = diversity_report(same)
    assert rep["mode_collapse"] is True
    assert rep["distinct_2"] < DISTINCT2_MIN
    assert rep["score_stdev"] < SCORE_STDEV_MIN


def test_diversity_report_accepts_varied():
    varied = [
        {"answer": {"scores": {"overall_impression": s},
                    "verbatims": {"a": t}}}
        for s, t in zip(
            (3, 5, 7, 9, 6),
            ("спор вышел живым и убедительным для меня",
             "картинка хороша, сюжет провисает во второй половине",
             "герой раздражает, зато музыка спасает",
             "не мой жанр совсем, выключил бы сразу",
             "неплохо, но ничего особенно не запомнилось"),
            strict=True,
        )
    ]
    rep = diversity_report(varied)
    assert rep["mode_collapse"] is False


def test_diversity_report_handles_flat_answers():
    """Артефакт до #18 был голым списком ответов — читать его надо тоже."""
    rep = diversity_report([{"scores": {"overall_impression": 7},
                             "verbatims": {"a": "текст"}}])
    assert rep["samples"] == 1
