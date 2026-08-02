"""Finder — движок поиска ближайших респондентов по Persona DNA.

Метрика сходства (задача #25, CDD: «сходство через вектор»):

    similarity = w_demo * demo_match + w_big5 * big5_sim + w_values * values_overlap

где:

- **demo_match** (вес 0.4) — доля совпадающих демографических полей
  (gender, age_group, geo, city, children). Каждое поле равно 1.0 при точном
  совпадении, 0.0 иначе; возраст — линейный коэффициент близости
  (1 - |Δage| / 80, ограниченный [0, 1]).
- **big5_sim** (вес 0.3) — 1 - euclidean(dna_big5, proxy_big5) / max_dist,
  где proxy_big5 выводится из ответов респондента (агора-баллы, восприятие,
  NPS). max_dist = sqrt(5 * 4^2) = sqrt(80).
- **values_overlap** (вес 0.3) — коэффициент Жаккара |A ∩ B| / |A ∪ B|
  по спискам ценностей DNA и респондента.

Все компоненты ∈ [0, 1], итоговый score ∈ [0, 1].
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --- пути ---

_AGENT_CORE = Path(__file__).resolve().parent.parent.parent  # services/agent-core
_REPO_ROOT = _AGENT_CORE.parent.parent  # AGORA/

CORPUS_PATH = _REPO_ROOT / "data" / "grounding" / "unified_respondent_sessions.json"

# --- веса метрики (сумма = 1.0) ---

W_DEMO: float = 0.4
W_BIG5: float = 0.3
W_VALUES: float = 0.3

# Максимальное евклидово расстояние по Big Five: 5 измерений, диапазон 1–5
# → max per-dim = 4 → max dist = sqrt(5 * 16) = sqrt(80) ≈ 8.944
_MAX_BIG5_DIST: float = math.sqrt(80.0)

# Поля демографии для сравнения
_DEMO_FIELDS: tuple[str, ...] = ("gender", "age_group", "geo", "city", "children")

# OCEAN-поля по порядку
_OCEAN: tuple[str, ...] = (
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FindConfig:
    """Параметры поиска.

    Fields:
        top_k: сколько ближайших соседей вернуть (1–200, по умолчанию 10).
        min_similarity: отсечь соседей с score ниже порога (0–1, по умолчанию 0.0).
        exclude_ids: набор respondent_id для исключения (например, held-out).
        weights: переопределение весов (demo, big5, values). Должны суммироваться в 1.0.
    """

    top_k: int = 10
    min_similarity: float = 0.0
    exclude_ids: set[str] = field(default_factory=set)
    weights: tuple[float, float, float] = (W_DEMO, W_BIG5, W_VALUES)

    def __post_init__(self) -> None:
        if not (1 <= self.top_k <= 500):
            raise ValueError(f"top_k должен быть 1–500, получено {self.top_k}")
        if not (0.0 <= self.min_similarity <= 1.0):
            raise ValueError(
                f"min_similarity должен быть 0–1, получено {self.min_similarity}"
            )
        s = sum(self.weights)
        if abs(s - 1.0) > 0.01:
            raise ValueError(f"веса должны суммироваться в 1.0, сумма = {s}")


@dataclass
class NeighborMatch:
    """Один сосед — результат поиска.

    Fields:
        respondent_id: ID из корпуса.
        similarity: итоговый score ∈ [0, 1].
        components: разбивка по компонентам {demo, big5, values}.
        respondent: полная запись респондента (для инспекции).
    """

    respondent_id: str
    similarity: float
    components: dict[str, float]
    respondent: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Сериализует в dict (для API-ответа)."""
        return {
            "respondent_id": self.respondent_id,
            "similarity": round(self.similarity, 4),
            "components": {
                k: round(v, 4) for k, v in self.components.items()
            },
            "socio_demographics": self.respondent.get("socio_demographics", {}),
            "content_under_test": self.respondent.get("content_under_test", {}),
        }


# ---------------------------------------------------------------------------
# RespondentFinder
# ---------------------------------------------------------------------------


class RespondentFinder:
    """Поиск ближайших респондентов в корпусе.

    Использование::

        finder = RespondentFinder.from_corpus()
        results = finder.find(persona_dna, FindConfig(top_k=10))
    """

    def __init__(self, records: list[dict[str, Any]]):
        self.records = records
        # Предвычисляем proxy Big Five для каждого респондента один раз
        self._proxy_cache: dict[str, dict[str, int]] = {}
        for r in records:
            rid = r.get("respondent_id", "")
            if rid:
                self._proxy_cache[rid] = _proxy_big_five(r)

    @classmethod
    def from_corpus(cls, path: Path | None = None) -> RespondentFinder:
        """Создаёт finder из канонического корпуса."""
        p = path or CORPUS_PATH
        records = json.loads(p.read_text("utf-8"))
        if not records:
            raise ValueError("корпус пуст — невозможно построить finder")
        return cls(records)

    def find(
        self,
        persona_dna: dict[str, Any],
        config: FindConfig | None = None,
    ) -> list[NeighborMatch]:
        """Находит top-K ближайших респондентов к persona_dna.

        Args:
            persona_dna: объект Persona DNA (соответствует schema).
            config: параметры поиска (по умолчанию — FindConfig()).

        Returns:
            Список NeighborMatch, отсортированный по убыванию similarity.
        """
        cfg = config or FindConfig()
        w_demo, w_big5, w_values = cfg.weights

        candidates: list[NeighborMatch] = []
        for r in self.records:
            rid = r.get("respondent_id", "")
            if rid in cfg.exclude_ids:
                continue

            demo = _demo_similarity(persona_dna, r)
            big5 = _big5_similarity(
                persona_dna, self._proxy_cache.get(rid, _proxy_big_five(r))
            )
            vals = _values_overlap(persona_dna, r)

            score = w_demo * demo + w_big5 * big5 + w_values * vals
            # Clamp для уверенности
            score = max(0.0, min(1.0, score))

            if score >= cfg.min_similarity:
                candidates.append(
                    NeighborMatch(
                        respondent_id=rid,
                        similarity=score,
                        components={
                            "demo": round(demo, 4),
                            "big5": round(big5, 4),
                            "values": round(vals, 4),
                        },
                        respondent=r,
                    )
                )

        candidates.sort(key=lambda m: m.similarity, reverse=True)
        return candidates[: cfg.top_k]


# ---------------------------------------------------------------------------
# Similarity components
# ---------------------------------------------------------------------------


def _demo_similarity(dna: dict[str, Any], respondent: dict[str, Any]) -> float:
    """Demographic match: доля совпадающих полей (0–1).

    Поля: gender, age_group, geo, city, children.
    Возраст (числовой) — линейная близость: 1 - |Δage|/80.
    Остальные — бинарное совпадение.
    """
    dna_demo = dna.get("demographics", {})
    r_demo = respondent.get("socio_demographics", {})

    scores: list[float] = []

    for f in _DEMO_FIELDS:
        if f == "age":
            # Числовой возраст — линейная близость
            d_age = dna_demo.get("age")
            r_age = r_demo.get("age")
            if d_age is not None and r_age is not None:
                try:
                    diff = abs(int(d_age) - int(r_age))
                    scores.append(max(0.0, 1.0 - diff / 80.0))
                except (TypeError, ValueError):
                    scores.append(0.0)
            else:
                scores.append(0.0)
        else:
            d_val = dna_demo.get(f)
            r_val = r_demo.get(f)
            if d_val is not None and r_val is not None and d_val == r_val:
                scores.append(1.0)
            else:
                scores.append(0.0)

    return sum(scores) / len(scores) if scores else 0.0


def _big5_similarity(dna: dict[str, Any], proxy: dict[str, int]) -> float:
    """Big Five similarity: 1 - euclidean_dist / max_dist.

    Args:
        dna: Persona DNA с полем big_five.
        proxy: прокси-Big Five респондента (из _proxy_big_five).
    """
    dna_b5 = dna.get("big_five", {})
    if not dna_b5 or not proxy:
        return 0.0

    sq_sum = 0.0
    n = 0
    for trait in _OCEAN:
        d_val = dna_b5.get(trait)
        r_val = proxy.get(trait)
        if d_val is not None and r_val is not None:
            try:
                diff = float(d_val) - float(r_val)
                sq_sum += diff * diff
                n += 1
            except (TypeError, ValueError):
                pass

    if n == 0:
        return 0.0

    dist = math.sqrt(sq_sum)
    # Нормализуем: 1 - dist / max_dist
    return max(0.0, 1.0 - dist / _MAX_BIG5_DIST)


def _values_overlap(dna: dict[str, Any], respondent: dict[str, Any]) -> float:
    """Values overlap: коэффициент Жаккара по списку ценностей.

    Args:
        dna: Persona DNA с values_and_beliefs.important_values.
        respondent: запись корпуса с psychographics_and_values.important_values.
    """
    dna_vals: set[str] = set()
    try:
        dna_vals = set(
            dna.get("values_and_beliefs", {}).get("important_values", [])
        )
    except (TypeError, AttributeError):
        pass

    r_vals: set[str] = set()
    try:
        r_vals = set(
            respondent.get("psychographics_and_values", {}).get(
                "important_values", []
            )
        )
    except (TypeError, AttributeError):
        pass

    if not dna_vals and not r_vals:
        return 0.0

    union = dna_vals | r_vals
    if not union:
        return 0.0

    intersection = dna_vals & r_vals
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Proxy Big Five inference from respondent data
# ---------------------------------------------------------------------------


def _proxy_big_five(respondent: dict[str, Any]) -> dict[str, int]:
    """Выводит прокси-оценки Big Five из ответов респондента.

    Респонденты корпуса не имеют прямых OCEAN-оценок. Мы выводим прокси из
    доступных данных:

    - **Openness** — из интереса к контенту (interest_level) и разнообразия
      эмоций. Высокий интерес + много эмоций → выше openness.
    - **Conscientiousness** — из того, насколько детально респондент
      отвечает (длина qualitative_verbatims). Длинные развёрнутые ответы →
      выше conscientiousness.
    - **Extraversion** — из количества focus_group_verbatims и эмоциональности.
      Много цитат → выше extraversion.
    - **Agreeableness** — из общего впечатления (overall_impression) и NPS.
      Высокие оценки → выше agreeableness.
    - **Neuroticism** — из негативных эмоций и низкой оценки реализма.
      Негативные эмоции / нереалистичность → выше neuroticism.

    Все оценки — целые 1–5.
    """
    # --- Interest → Openness ---
    interest_map = {
        "Очень интересен": 5,
        "Скорее интересен": 4,
        "Нейтрально": 3,
        "Скорее не интересен": 2,
        "Совершенно не интересен": 1,
    }
    perception = respondent.get("perception_and_retention", {})
    interest = interest_map.get(
        perception.get("interest_level", ""), 3
    )
    # Разнообразие эмоций повышает openness
    emotions = perception.get("emotions_evoked", [])
    n_emotions = len(emotions) if isinstance(emotions, list) else 0
    openness = min(5, max(1, interest + (1 if n_emotions >= 3 else 0)))

    # --- Verbatim length → Conscientiousness ---
    qv = respondent.get("qualitative_verbatims", {})
    total_text = ""
    for v in (
        qv.get("why_impression"),
        qv.get("general_impression_comment"),
        qv.get("idea_comprehension_comment"),
    ):
        if v and isinstance(v, str):
            total_text += v
    vlen = len(total_text)
    if vlen > 200:
        conscientiousness = 5
    elif vlen > 100:
        conscientiousness = 4
    elif vlen > 50:
        conscientiousness = 3
    elif vlen > 20:
        conscientiousness = 2
    else:
        conscientiousness = 1

    # --- Focus group participation → Extraversion ---
    fg_verbatims = respondent.get("focus_group_verbatims", [])
    n_fg = len(fg_verbatims) if isinstance(fg_verbatims, list) else 0
    if n_fg >= 4:
        extraversion = 5
    elif n_fg >= 3:
        extraversion = 4
    elif n_fg >= 2:
        extraversion = 3
    elif n_fg >= 1:
        extraversion = 2
    else:
        extraversion = 1

    # --- Overall impression + NPS → Agreeableness ---
    scores = respondent.get("agora_core_scores_1_to_10", {})
    overall = scores.get("overall_impression", 5)
    nps = perception.get("recommendation_nps_1_to_10", 5)
    # Нормализуем 1-10 → 1-5
    avg_positive = ((overall or 5) + (nps or 5)) / 2.0
    agreeableness = min(5, max(1, round(avg_positive / 2.0)))

    # --- Negative emotions + low realism → Neuroticism ---
    negative_markers = {
        "Грусть", "Страх", "Раздражение", "Тревога", "Отвращение",
        "Злость", "Будет способствовать усилению пессимизма",
    }
    emo_set = set(emotions) if isinstance(emotions, list) else set()
    n_neg = len(emo_set & negative_markers)
    realism = perception.get("realism_perception", "")
    realism_low = "нереалистич" in (realism or "").lower()
    neuroticism = min(5, max(1, 2 + n_neg + (1 if realism_low else 0)))

    return {
        "openness": openness,
        "conscientiousness": conscientiousness,
        "extraversion": extraversion,
        "agreeableness": agreeableness,
        "neuroticism": neuroticism,
    }


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def find_similar_respondents(
    persona_dna: dict[str, Any],
    config: FindConfig | None = None,
    corpus_path: Path | None = None,
) -> list[NeighborMatch]:
    """Находит ближайших респондентов к persona_dna.

    Это точка входа, используемая API-маршрутом и CDD-тестом.

    Args:
        persona_dna: объект Persona DNA (соответствует schema).
        config: параметры поиска (по умолчанию — FindConfig()).
        corpus_path: путь к корпусу (по умолчанию — канонический).

    Returns:
        Список NeighborMatch, отсортированный по убыванию similarity.
    """
    finder = RespondentFinder.from_corpus(corpus_path)
    return finder.find(persona_dna, config)