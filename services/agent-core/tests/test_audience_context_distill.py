"""The uploaded audience context is distilled and kept separate from grounding."""

from agent_core.persona import generator, tasks
from agent_core.portraits import distill


def test_context_file_reuses_portrait_distill(monkeypatch):
    seen = {}

    def fake_distill(records, segment_key, prompt_template=None, **kwargs):
        seen["records"] = records
        seen["segment"] = segment_key
        seen["prompt"] = prompt_template
        return "# distilled context"

    monkeypatch.setattr(distill, "distill_portrait_llm", fake_distill)
    result = distill.distill_context_file(
        "Ниша: авторское кино.",
        prompt_template="portrait.distill",
    )

    assert result == "# distilled context"
    assert seen["segment"] == "уточнение заказчика"
    assert seen["prompt"] == "portrait.distill"
    assert seen["records"][0]["context_text"] == "Ниша: авторское кино."


def test_context_is_a_separate_prompt_section_without_moving_grounding():
    gen = generator.PersonaGenerator.from_corpus()
    config = generator.GenerationConfig(
        size=2,
        seed=11,
        audience_context="# Портрет ниши\nЛюбят камерные истории.",
    )

    prompt_context = gen.build_prompt_context(config)
    assert prompt_context["audience_context"].startswith("# Портрет ниши")
    assert prompt_context["segment_distributions"]
    assert prompt_context["score_means"]
    assert gen.dist.score_means == generator.CorpusDistribution.from_corpus(gen.records).score_means


def test_task_distills_before_constructing_generation_config(monkeypatch):
    seen = {}

    def fake_distill(text, **kwargs):
        seen["text"] = text
        return "# distilled"

    monkeypatch.setattr(tasks, "distill_context_file", fake_distill)
    monkeypatch.setattr(tasks, "load_prompt_template", lambda: "portrait.distill")

    config = generator.GenerationConfig(
        **tasks._prepare_generation_config(
            {"size": 1, "seed": 1, "audience_context": "raw file"}
        )
    )

    assert seen["text"] == "raw file"
    assert config.audience_context == "# distilled"


def test_binary_context_is_loaded_by_worker_before_generation_config(monkeypatch):
    monkeypatch.setattr(
        tasks,
        "_load_context_file_portrait",
        lambda file_id, tenant_id: f"# distilled {file_id} for {tenant_id}",
    )

    config = generator.GenerationConfig(
        **tasks._prepare_generation_config(
            {"size": 1, "seed": 1, "audience_context_file_id": "file-1"},
            "tenant-1",
        )
    )

    assert config.audience_context == "# distilled file-1 for tenant-1"
