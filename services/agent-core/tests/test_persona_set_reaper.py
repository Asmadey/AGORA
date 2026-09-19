"""CDD checks for stale persona-set cleanup and deployment preflight."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TASKS = ROOT / "services" / "agent-core" / "agent_core" / "persona" / "tasks.py"
CELERY = ROOT / "services" / "agent-core" / "agent_core" / "celery_app.py"
PREFLIGHT = ROOT / "infra" / "preflight.py"
DEPLOY = ROOT / "infra" / "deploy.sh"


def test_stale_persona_set_is_failed_and_fresh_one_is_untouched() -> None:
    """The decision is pure arithmetic over fake rows, not a live database."""
    from agent_core.maintenance.persona_sets import reap_stale

    now = datetime.now(UTC)
    rows = [
        {
            "id": "old",
            "status": "generating",
            "progress_at": now - timedelta(minutes=6),
            "generated_count": 12,
        },
        {
            "id": "fresh",
            "status": "generating",
            "progress_at": now - timedelta(minutes=4),
            "generated_count": 7,
        },
    ]

    result = reap_stale(rows, now=now)

    assert [item["id"] for item in result] == ["old"]
    assert "5" in result[0]["reason"]
    assert "12" in result[0]["reason"]


def test_preflight_rejects_generating_persona_sets_and_accepts_ready_only() -> None:
    """Preflight must inspect persona_sets before a worker rebuild."""
    spec = importlib.util.spec_from_file_location("agora_preflight", PREFLIGHT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Cursor:
        def __init__(self, generating: int):
            self.generating = generating
            self.result = None

        def execute(self, sql: str) -> None:
            assert "persona_sets" in sql
            self.result = (self.generating,)

        def fetchone(self):
            return self.result

    class Connection:
        def __init__(self, generating: int):
            self.cursor_value = Cursor(generating)

        def cursor(self):
            class Context:
                def __enter__(inner):
                    return self.cursor_value

                def __exit__(inner, *args):
                    return False

            return Context()

    seen: list[tuple[str, str, str]] = []
    module.report = lambda name, status, detail="": seen.append((name, status, detail))
    module.check_persona_sets(Connection(1))
    assert seen[-1][1] == "fail"
    assert "generating" in seen[-1][2]

    seen.clear()
    module.check_persona_sets(Connection(0))
    assert seen[-1][1] == "ok"


def test_deploy_checks_both_tables_before_compose_build() -> None:
    """Ворота стоят до сборки и смотрят ОБЕ таблицы.

    Раньше здесь проверялось, что deploy.sh зовёт `python3 infra/preflight.py`.
    Проверка была верной по смыслу и неверной по существу: preflight ходит в
    базу по адресу из .env.local, а это имя докер-сети (`postgres:5432`),
    которое с хоста не резолвится. На боевом сервере ворота падали с
    «Temporary failure in name resolution» ДО любой сборки, то есть развернуть
    было нельзя вообще ничего, и тест этого не ловил — он читал текст скрипта,
    а не его поведение.

    Поэтому теперь проверяется то, что ворота действительно делают: спрашивают
    обе таблицы у базы тем способом, который с хоста работает.
    """
    source = DEPLOY.read_text("utf-8")
    gate = source.index("docker exec agora-postgres-1 psql")
    build = source.index("docker compose -f")
    assert gate < build, "ворота обязаны стоять до сборки"
    prefix = source[:build]
    assert "persona_sets" in prefix, "ворота не смотрят в persona_sets"
    assert "tasks" in prefix, "ворота не смотрят в tasks"
    assert "generating" in prefix and "RUNNING" in prefix


def test_celery_wires_persona_set_reaper() -> None:
    source = CELERY.read_text("utf-8")
    assert "agora.reap_persona_sets" in source
    assert "reap-persona-sets" in source


@pytest.mark.parametrize("needle", ["progress_at", "generated_count = %s"])
def test_progress_schema_and_write_are_present(needle: str) -> None:
    migration = ROOT / "infra" / "postgres" / "init" / "56_persona_sets_progress_at.sql"
    source = (migration.read_text("utf-8") if migration.exists() else "") + TASKS.read_text("utf-8")
    assert needle in source
