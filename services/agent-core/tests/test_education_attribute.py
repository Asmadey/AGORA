"""Красные ворота для образования в атрибуте персоны и аудитории."""

from __future__ import annotations

from collections import Counter

import pytest

from agent_core.persona.generator import GenerationConfig, PersonaGenerator


def _personas(size: int = 2_000, **kwargs: object) -> list[dict]:
    generator = PersonaGenerator.from_corpus()
    out: list[dict] = []
    for batch, offset in enumerate(range(0, size, 500)):
        out.extend(
            generator.generate(
                GenerationConfig(
                    size=min(500, size - offset),
                    seed=20260919 + batch,
                    **kwargs,
                )
            )
        )
    return out


def test_underage_personas_cannot_have_higher_education() -> None:
    personas = _personas()
    forbidden = {"высшее", "неполное высшее"}
    assert all(
        not (
            persona["demographics"]["age"] < 18
            and persona["lifestyle_and_interests"]["education_level"] in forbidden
        )
        for persona in personas
    )


def test_age_gates_allow_only_canonical_levels() -> None:
    for persona in _personas():
        age = persona["demographics"]["age"]
        level = persona["lifestyle_and_interests"]["education_level"]
        if age <= 17:
            assert level == "среднее"
        elif age <= 21:
            assert level in {"среднее", "среднее специальное", "неполное высшее"}
        else:
            assert level in {
                "среднее",
                "среднее специальное",
                "неполное высшее",
                "высшее",
            }


def test_group_shares_match_external_passport() -> None:
    expected = {"18-24": 5, "25-34": 41, "35-44": 36, "45-59": 27, "60+": 19}
    for group, expected_percent in expected.items():
        counts: Counter[str] = Counter(
            persona["lifestyle_and_interests"]["education_level"]
            for persona in _personas(10_000, age_groups=[group])
        )
        total = sum(counts.values())
        actual_percent = 100 * counts["высшее"] / total
        assert abs(actual_percent - expected_percent) <= 1.0, (
            group,
            actual_percent,
            expected_percent,
        )


def test_restrict_has_higher_reweights_age_and_levels() -> None:
    personas = _personas(
        500,
        age_groups=["14-17", "18-24", "25-34", "35-44", "45-59", "60+"],
        education=["есть высшее"],
    )
    assert personas
    assert all(p["lifestyle_and_interests"]["education_level"] == "высшее" for p in personas)
    assert all(p["demographics"]["age_group"] != "14-17" for p in personas)


def test_impossible_intersection_is_rejected() -> None:
    generator = PersonaGenerator.from_corpus()
    with pytest.raises(ValueError, match="образован|14-17|невозмож"):
        generator.generate(
            GenerationConfig(
                size=40,
                seed=1,
                age_groups=["14-17"],
                education=["есть высшее"],
            )
        )


def test_same_seed_is_deterministic_with_education_filter() -> None:
    generator = PersonaGenerator.from_corpus()
    config = GenerationConfig(
        size=100,
        seed=77,
        education=["нет высшего"],
    )
    assert generator.generate(config) == generator.generate(config)
