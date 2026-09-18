"""CDD checks for batched and resumable audience generation."""

from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from agent_core import db, tracing
from agent_core.persona import enrich, generator, tasks

ROOT = Path(__file__).resolve().parents[3]
TASKS = ROOT / "services" / "agent-core" / "agent_core" / "persona" / "tasks.py"


def test_resume_tail() -> None:
    source = TASKS.read_text("utf-8")
    assert 'payload.get("resume")' in source
    assert "count(*) FROM personas" in source
    assert "[start:]" in source
    assert "enrich_personas" in source
    assert "PROGRESS_EVERY" in source

    class FakeGenerator:
        dist = type("Dist", (), {"verbatims": []})()

        def generate_named(self, config):
            return [(f"p{i}", {"narrative": f"n{i}", "seed": i}) for i in range(config.size)]

    model_phases: list[str] = []
    written: list[tuple[int, int]] = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.validation = "response_schema" in kwargs

        def complete(self, *, prompt: str) -> str:
            del prompt
            model_phases.append("validation" if self.validation else "enrichment")
            return (
                json.dumps({"consistent": True, "confidence": 1.0, "issues": []})
                if self.validation
                else "Связный портрет персоны длиной больше минимального порога. " * 4
            )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        tasks,
        "_begin_generation",
        lambda *args: {
            "size": 40,
            "generation_config": {"size": 40, "seed": 42, "use_llm": True},
            "seed": 42,
            "corpus_snapshot_id": None,
            "status": "generating",
            "generated_count": 12,
            "previous_status": "failed",
        },
    )
    monkeypatch.setattr(
        tasks,
        "_write_persona_batch",
        lambda tenant_id, set_id, **kwargs: (
            written.append((kwargs["expected_start"], len(kwargs["personas"])))
            or kwargs["expected_start"] + len(kwargs["personas"])
        ),
    )
    monkeypatch.setattr(tasks, "_load_portraits", lambda tenant_id: {})
    monkeypatch.setattr(enrich, "QwenTextClient", FakeClient)
    monkeypatch.setattr(
        generator.PersonaGenerator,
        "from_corpus",
        classmethod(lambda cls: FakeGenerator()),
    )
    monkeypatch.setattr(tracing, "run", lambda **kwargs: nullcontext())

    try:
        result = tasks.generate_audience.run(
            {
                "persona_set_id": "set-id",
                "tenant_id": "tenant-id",
                "resume": True,
                "settings_snapshot": {},
            }
        )
    finally:
        monkeypatch.undo()

    assert result["status"] == "ready"
    assert model_phases.count("enrichment") == 28
    assert sum(size for _, size in written) == 28
    assert written[0][0] == 12


def test_ready_only_when_complete() -> None:
    source = TASKS.read_text("utf-8")
    assert "status = CASE WHEN" in source
    assert "'ready'" in source
    assert "generated_count" in source
    assert "size" in source
    assert "progress_at" in source


def test_ready_only_when_complete_write(monkeypatch) -> None:
    import psycopg

    monkeypatch.setenv("DATABASE_URL", "postgresql://test.invalid/test")

    class Cursor:
        def __init__(self, current: int):
            self.current = current
            self.result = None
            self.last_update = ""
            self.rowcount = 1

        def execute(self, sql, params):
            if "SELECT size" in sql:
                self.result = (40,)
            elif "SELECT count(*)" in sql:
                self.result = (self.current,)
            elif sql.startswith("UPDATE persona_sets"):
                self.last_update = sql
                self.rowcount = 1

        def fetchone(self):
            return self.result

    def run_write(current: int) -> str:
        cursor = Cursor(current)
        monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: nullcontext(object()))
        monkeypatch.setattr(db, "tenant_scope", lambda *args: nullcontext(cursor))
        tasks._write_persona_batch(
            "tenant-id",
            "set-id",
            names=["name"],
            personas=[{"narrative": "n", "seed": 1}],
            verdicts=[{}],
            expected_start=current,
            total=40,
        )
        return cursor.last_update

    assert "'ready'" in run_write(39)
    assert "'generating'" in run_write(12)


def test_retry_resumes() -> None:
    source = TASKS.read_text("utf-8")
    assert "self.retry" in source
    assert '"resume": True' in source
    assert "PersonaSetGone" in source


def test_retry_resumes_payload(monkeypatch) -> None:
    class RetryRaised(Exception):
        pass

    def fail_before_work(*args):
        raise RuntimeError("temporary model outage")

    captured: dict[str, object] = {}

    def retry(*, args, exc, countdown):
        captured["payload"] = args[0]
        captured["exc"] = exc
        captured["countdown"] = countdown
        raise RetryRaised

    monkeypatch.setattr(tasks, "_begin_generation", fail_before_work)
    monkeypatch.setattr(tasks.generate_audience, "retry", retry)
    monkeypatch.setattr(tasks.generate_audience.request, "retries", 0, raising=False)

    try:
        tasks.generate_audience.run(
            {"persona_set_id": "set-id", "tenant_id": "tenant-id"}
        )
    except RetryRaised:
        pass
    else:
        raise AssertionError("temporary failure did not request Celery retry")

    assert captured["payload"]["resume"] is True
    assert captured["countdown"] > 0
