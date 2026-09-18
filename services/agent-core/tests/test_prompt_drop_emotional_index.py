"""Контракт удаления платного, но не читаемого индекса из analytics.report."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROMPT = ROOT / "prompts" / "analytics.report.md"
MIGRATION = (
    ROOT
    / "infra"
    / "postgres"
    / "init"
    / "49_prompts_seed_remove_emotional_index.sql"
)
AGGREGATE = (
    ROOT / "services" / "agent-core" / "agent_core" / "analytics" / "aggregate.py"
)


def test_analytics_prompt_and_forward_migration_drop_emotional_index():
    prompt = PROMPT.read_text(encoding="utf-8")
    migration = MIGRATION.read_text(encoding="utf-8")

    assert "emotional_index" not in prompt
    assert "emotional_index" not in migration
    assert "analytics.report" in migration
    assert "version = version + 1" in migration
    assert "AND version = 2" in migration
    assert "ON CONFLICT" not in migration
    assert "rationales" in prompt


def test_aggregate_does_not_reintroduce_removed_derived_fields():
    source = AGGREGATE.read_text(encoding="utf-8")

    assert "_emotional_index" not in source
    assert "_top_emotions" not in source
