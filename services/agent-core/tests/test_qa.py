"""
Модульные тесты QA-агента (#19).

CDD-тест задачи (evals/tests/test_task19_qa.py) проверяет требование целиком —
подсадку ловим, чистое не трогаем, эскалация по порогу. Здесь проверяются
кирпичи по отдельности: разбор таймкодов, распознавание намерения досмотреть,
разбор вердикта судьи и сборка URL агента-перепроверщика.

Разделение не дублирование. CDD-тест ответит «QA сломан», модульный — «сломан
разбор H:MM:SS», и второй ответ экономит проход.
"""

from __future__ import annotations

import json

import pytest

from agent_core.config import ConfigError, QaConfig
from agent_core.qa.checks import (
    consistency_reasons,
    grounding_reasons,
    retention_stance,
    timecodes,
)
from agent_core.qa.judge import parse_verdict, render

# ─── Таймкоды ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("text", "expected"), [
    ("00:10 спор на кухне", [10]),
    ("07:45 сцена в лесу", [465]),
    ("на 1:02:03 всё меняется", [3723]),
    ("с 00:10 до 00:40", [10, 40]),
    # Не таймкоды: секунды вне 0–59 и голые числа через двоеточие в тексте.
    ("счёт 10:75 в пользу гостей", []),
    ("никаких таймкодов", []),
])
def test_timecodes(text, expected):
    assert timecodes(text) == expected


def test_timecode_h_mm_ss_not_split_in_two():
    """H:MM:SS не должен разваливаться на два таймкода — иначе 1:02:03 даст 62 с."""
    assert timecodes("1:02:03") == [3723]


# ─── Намерение досмотреть ────────────────────────────────────────────────────


@pytest.mark.parametrize(("value", "expected"), [
    ("скорее досмотреть", "continue"),
    ("Скорее хотелось досмотреть до конца", "continue"),
    ("скорее выключить", "stop"),
    ("выключил бы", "stop"),
    ("Скорее хотелось остановить просмотр", "stop"),
    # Отрицание проверяется раньше: «не досмотрел бы» содержит и «досмотр».
    ("не досмотрел бы", "stop"),
    ("Затрудняюсь ответить", "unknown"),
    ("", "unknown"),
    (None, "unknown"),
])
def test_retention_stance(value, expected):
    assert retention_stance(value) == expected


# ─── Правила согласованности ─────────────────────────────────────────────────


def _answer(**over):
    score = over.get("overall", 7)
    return {
        "scores": {"overall_impression": score, "plot": score, "acting": score,
                   "music": score, "cinematography": score},
        "perception": {
            "retention_intent": over.get("retention", "скорее досмотреть"),
            "recommendation_nps_1_to_10": over.get("nps", score),
        },
        "survey_answers": over.get("survey_answers", {"q1": score}),
        "verbatims": over.get("verbatims", {"why_impression": "живо сыграно"}),
        "grounding_refs": over.get("refs", ["00:10 спор на кухне"]),
    }


def test_clean_answer_has_no_reasons():
    assert consistency_reasons(_answer()) == []


def test_high_score_with_intent_to_stop_is_caught():
    reasons = consistency_reasons(_answer(overall=10, nps=10, retention="выключил бы"))
    assert any("прекратить просмотр" in r for r in reasons)


def test_low_score_with_intent_to_finish_is_caught():
    reasons = consistency_reasons(_answer(overall=2, nps=2, retention="досмотреть до конца"))
    assert any("намерении досмотреть" in r for r in reasons)


def test_middle_scores_are_not_flagged():
    """«На шесть, но выключил бы» — обычная зрительская позиция, не противоречие."""
    assert consistency_reasons(_answer(overall=6, nps=6, retention="скорее выключить")) == []


def test_score_out_of_scale_is_caught():
    assert any("вне шкалы" in r for r in consistency_reasons(_answer(overall=12)))


def test_gap_between_impression_and_nps_is_caught():
    assert any("против рекомендации" in r for r in consistency_reasons(_answer(overall=9, nps=2)))


def test_unanswered_survey_question_is_caught():
    survey = {"questions": [{"id": "q1"}, {"id": "q2"}]}
    reasons = consistency_reasons(_answer(survey_answers={"q1": 7}), survey)
    assert any("q2" in r for r in reasons)


def test_empty_verbatims_are_caught():
    assert any("вербатимы пусты" in r for r in consistency_reasons(_answer(verbatims={})))


# ─── Правила заземления ──────────────────────────────────────────────────────


PACK = {"duration_sec": 100.0}


def test_timecode_beyond_duration_is_caught():
    reasons = grounding_reasons(_answer(refs=["07:45 сцена в лесу"]), PACK)
    assert any("за пределами ролика" in r for r in reasons)


def test_timecode_in_verbatim_is_caught_too():
    """Выдумка чаще попадает в текст, чем в поле refs: там она у персоны на виду."""
    answer = _answer(verbatims={"why_impression": "на 09:30 меня зацепило"})
    assert any("вербатим" in r for r in grounding_reasons(answer, PACK))


def test_timecode_at_the_edge_is_allowed():
    """01:40 при длительности 99.6 с — округление склейки, а не выдумка."""
    assert grounding_reasons(_answer(refs=["01:40 финал"]), {"duration_sec": 99.6}) == []


def test_empty_refs_are_caught():
    assert any("grounding_refs пуст" in r for r in grounding_reasons(_answer(refs=[]), PACK))


def test_unknown_duration_does_not_flag_timecodes():
    """Без длительности сравнивать не с чем — молчим, а не флагуем каждый ответ."""
    assert grounding_reasons(_answer(refs=["07:45 сцена в лесу"]), {}) == []


# ─── Разбор вердикта судьи ───────────────────────────────────────────────────


def test_verdict_confidence_is_parsed():
    parsed = parse_verdict(json.dumps({"verdict": "ok", "confidence": 0.83}))
    assert parsed.verdict == "ok"
    assert parsed.confidence == 0.83


def test_missing_confidence_is_zero_not_one():
    """Молчание про уверенность — не уверенность. Иначе эскалация обходится молчанием."""
    parsed = parse_verdict(json.dumps({"verdict": "ok"}))
    assert parsed.confidence == 0.0
    assert any("confidence" in r for r in parsed.reasons)


def test_verdict_is_derived_from_profile_field_when_absent():
    parsed = parse_verdict(json.dumps({"grounded": False, "confidence": 0.9}))
    assert parsed.verdict == "regenerate"


def test_low_consistency_score_means_regenerate():
    parsed = parse_verdict(json.dumps({"consistency_score": 4, "confidence": 0.9}))
    assert parsed.verdict == "regenerate"


def test_fenced_json_is_parsed():
    """Модель регулярно оборачивает JSON в ```json — это поведение, а не сбой."""
    raw = '```json\n{"verdict": "ok", "confidence": 0.5}\n```'
    assert parse_verdict(raw).confidence == 0.5


def test_confidence_is_clamped():
    assert parse_verdict(json.dumps({"verdict": "ok", "confidence": 4})).confidence == 1.0


def test_render_serialises_dicts_as_json():
    """str(dict) дал бы одинарные кавычки, и судья спотыкался бы о них, а не о существо."""
    out = render("профиль: {{persona_dna}}", {"persona_dna": {"age": 30}})
    assert '"age": 30' in out
    assert "'age'" not in out


# ─── Политика эскалации ──────────────────────────────────────────────────────


def test_default_threshold_matches_env_example():
    """
    Порог в коде и в контракте окружения — одно число.

    Разойдясь, они дают разный порог в зависимости от того, скопировал ли
    оператор .env.example: у одного эскалация на трети ответов, у другого на
    десятой части, и оба уверены, что настройка одна. Расхождение ничего не
    ломает заметно — потому и нужна проверка.
    """
    from pathlib import Path

    from agent_core.config import DEFAULT_ESCALATION_CONFIDENCE

    env_example = Path(__file__).resolve().parents[3] / "apps" / "web" / ".env.example"
    if not env_example.is_file():
        pytest.skip("apps/web/.env.example недоступен из этой раскладки (образ воркера)")

    declared = None
    for line in env_example.read_text("utf-8").splitlines():
        if line.startswith("QA_ESCALATION_CONFIDENCE"):
            declared = float(line.split("=", 1)[1].split("#")[0].strip().strip('"'))
            break

    assert declared is not None, "QA_ESCALATION_CONFIDENCE не объявлен в .env.example"
    assert declared == DEFAULT_ESCALATION_CONFIDENCE


def test_escalation_disabled_without_agent_id(monkeypatch):
    monkeypatch.delenv("QA_ESCALATION_AGENT_ID", raising=False)
    assert QaConfig.from_env().escalation_enabled is False


def test_escalation_threshold_out_of_range_is_rejected(monkeypatch):
    monkeypatch.setenv("QA_ESCALATION_CONFIDENCE", "7")
    with pytest.raises(ConfigError):
        QaConfig.from_env()


def test_escalation_base_url_swaps_agent_segment():
    policy = QaConfig(escalation_agent_id="big-agent", escalation_confidence=0.7)
    url = policy.escalation_base_url(
        "https://agent.timeweb.cloud/api/v1/cloud-ai/agents/small-agent/v1"
    )
    assert url == "https://agent.timeweb.cloud/api/v1/cloud-ai/agents/big-agent/v1"


def test_escalation_accepts_full_url():
    policy = QaConfig(escalation_agent_id="https://other.example/v1/", escalation_confidence=0.7)
    assert policy.escalation_base_url("https://ignored/v1") == "https://other.example/v1"


def test_escalation_without_agent_segment_fails_loudly():
    """Тихий откат на основной агент означал бы штамп «перепроверено» без перепроверки."""
    policy = QaConfig(escalation_agent_id="big-agent", escalation_confidence=0.7)
    with pytest.raises(ConfigError):
        policy.escalation_base_url("https://api.example.com/v1")
