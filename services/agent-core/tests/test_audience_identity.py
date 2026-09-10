"""Generation-to-storage regression: retries must replace the entire identity.

The real generator, enrichment loop, validator and task run together; only
external model responses and database I/O are controlled. This is not live E2E.
"""

import json
from contextlib import nullcontext

import pytest

from agent_core import db, tracing
from agent_core.persona import enrich, tasks, validate
from agent_core.persona.generator import GenerationConfig, PersonaGenerator


@pytest.mark.parametrize("failure", [None, "enrich", "validation"])
@pytest.mark.parametrize("seed", [0, 1])
@pytest.mark.parametrize("rejections", [0, 1, 2, 3])
def test_saved_name_belongs_to_final_persona(monkeypatch, rejections, seed, failure):
    import psycopg

    generator = PersonaGenerator.from_corpus()
    config = dict(size=3, seed=seed, use_llm=True)
    original = generator.generate_named(GenerationConfig(**config))
    inserted = []

    class Cursor:
        def execute(self, sql, params):
            if sql.startswith("INSERT INTO personas"):
                inserted.append(params)

    class Client:
        def __init__(self, **kwargs):
            self.validator = "response_schema" in kwargs
            self.calls = 0

        def complete(self, *, prompt):
            self.calls += 1
            if self.validator:
                return json.dumps({
                    "consistent": self.calls > rejections,
                    "confidence": 1,
                    "issues": ["controlled rejection"] if self.calls <= rejections else [],
                })
            # The model is controlled; identity still comes from the real generator.
            return "Описание проверяемой персоны. " * 20

    monkeypatch.setenv("DATABASE_URL", "postgresql://test.invalid/test")
    monkeypatch.setattr(psycopg, "connect", lambda *a, **kw: nullcontext())
    monkeypatch.setattr(db, "tenant_scope", lambda *a: nullcontext(Cursor()))
    monkeypatch.setattr(tasks, "_update", lambda *a: None)
    monkeypatch.setattr(tasks, "_load_portraits", lambda *a: {})
    monkeypatch.setattr(tracing, "run", lambda **kw: nullcontext())
    monkeypatch.setattr(enrich, "QwenTextClient", Client)

    if failure == "enrich":
        real_enrich = enrich.enrich_personas

        def fail_replacement(personas, **kwargs):
            if len(personas) == 1:
                raise RuntimeError("replacement enrichment failed")
            return real_enrich(personas, **kwargs)

        monkeypatch.setattr(enrich, "enrich_personas", fail_replacement)
    elif failure == "validation":
        real_validate = validate.validate_set

        def fail_after_replacement(*args, **kwargs):
            real_validate(*args, **kwargs)
            raise RuntimeError("validation phase failed after replacement")

        monkeypatch.setattr(validate, "validate_set", fail_after_replacement)

    result = tasks.generate_audience.run({
        "persona_set_id": "test-set", "tenant_id": "test-tenant", "config": config,
    })
    assert result["status"] == "ready", result
    assert len(inserted) == config["size"]
    if failure:
        assert [row[1] for row in inserted] == [name for name, _ in original]
        assert all(row[4] == seed for row in inserted)
    for index, row in enumerate(inserted):
        stored_name, dna = row[1], json.loads(row[2])
        expected_name, expected_dna = (
            original[index] if dna["seed"] == config["seed"] else
            generator.generate_named(GenerationConfig(**{
                **config, "size": 1, "seed": dna["seed"],
            }))[0]
        )
        assert stored_name == expected_name, (
            f"Saved {stored_name} with {expected_name}'s profile: "
            f"gender={dna['demographics']['gender']}, seed={dna['seed']}"
        )
        assert dna["demographics"] == expected_dna["demographics"]
        assert row[3] == dna["narrative"]
        assert row[4] == dna["seed"]
