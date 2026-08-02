"""Respondent Matching — задача #25.

Поиск ближайших респондентов в grounding-корпусе по Persona DNA.

Сходство — взвешенная сумма трёх компонент:

  1. **Demographic match** (вес 0.4) — точное совпадение по полу, возрастной
     группе, гео, городу, наличию детей.
  2. **Big Five distance** (вес 0.3) — обратное евклидово расстояние по OCEAN,
     нормализованное в [0, 1]. Респонденты не имеют Big Five напрямую —
     прокси-оценки выводятся из баллов и восприятия (см. ``_proxy_big_five``).
  3. **Values overlap** (вес 0.3) — коэффициент Жаккара по списку ценностей.

Все компоненты ∈ [0, 1], итоговый score ∈ [0, 1].

Использование::

    from agent_core.matching import RespondentFinder, FindConfig

    finder = RespondentFinder.from_corpus()
    results = finder.find(persona_dna, FindConfig(top_k=10))
    # → list[NeighborMatch] с similarity ∈ [0, 1]
"""

from __future__ import annotations

from agent_core.matching.finder import (
    FindConfig,
    NeighborMatch,
    RespondentFinder,
    find_similar_respondents,
)

__all__ = [
    "FindConfig",
    "NeighborMatch",
    "RespondentFinder",
    "find_similar_respondents",
]