"""Проверка доставки охвата персон из узла analytics в расчёт анкеты."""

from agent_core.pipeline import nodes


def _persona(persona_id: str, age: int) -> dict:
    return {
        "id": persona_id,
        "dna": {"demographics": {"age": age, "gender": "жен", "geo": "центры субъектов"}},
    }


def _answer(persona_id: str) -> dict:
    return {
        "persona_id": persona_id,
        "replication": 0,
        "segment": {"age_group": "18-24", "geo": "центры субъектов"},
        "answer": {
            "scores": {"plot": 5},
            "survey_answers": {"q-score": 8},
        },
    }


def _state() -> dict:
    return {
        "task_id": "survey-scope-test",
        "tenant_id": "tenant-scope-test",
        "persona_ids": [f"p{i}" for i in range(20)],
        "persona_answers": [_answer(f"p{i}") for i in range(20)],
        "survey": {
            "questions": [
                {
                    "id": "q-score",
                    "number": 1,
                    "type": "scale",
                    "scaleMin": 0,
                    "scaleMax": 10,
                }
            ]
        },
    }


def test_analytics_node_counts_all_run_personas(monkeypatch):
    personas = [_persona(f"p{i}", 30 if i < 9 else 40) for i in range(20)]
    monkeypatch.setattr(nodes, "_load_personas", lambda state: personas)

    update = nodes.analytics(_state())

    audience = update["report"]["aggregate"]["survey"]["audience"]
    assert audience["total"] == 20


def test_target_slice_counts_personas_in_age_range(monkeypatch):
    personas = [_persona(f"p{i}", 30 if i < 9 else 40) for i in range(20)]
    monkeypatch.setattr(nodes, "_load_personas", lambda state: personas)

    update = nodes.analytics(_state())

    audience = update["report"]["aggregate"]["survey"]["audience"]
    assert audience["target"] == 9
