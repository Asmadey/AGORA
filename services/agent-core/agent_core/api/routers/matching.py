"""POST /api/matching/find — поиск ближайших респондентов по Persona DNA (задача #25).

Принимает JSON-тело:

    {
        "persona_dna": { ... PersonaDNA ... },
        "top_k": 10,            // 1–200, по умолчанию 10
        "min_similarity": 0.0,  // отсечка 0–1
        "exclude_ids": []       // список respondent_id для исключения
    }

Возвращает:

    {
        "matches": [ {respondent_id, similarity, components, ...}, ... ],
        "total": 10,
        "corpus_size": 165
    }

CDD: «поиск похожих респондентов возвращает осмысленных соседей на held-out
выборке». Сходство через вектор (Decision Log / PRD §7), TypeDB не используется.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_core.matching import FindConfig, find_similar_respondents

router = APIRouter(prefix="/api", tags=["matching"])


class MatchingRequest(BaseModel):
    """Тело запроса POST /api/matching/find."""

    persona_dna: dict[str, Any] = Field(
        ..., description="Persona DNA объект (соответствует persona-dna.schema.json)"
    )
    top_k: int = Field(default=10, ge=1, le=500, description="Количество соседей (1–500)")
    min_similarity: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Минимальный порог сходства"
    )
    exclude_ids: list[str] = Field(
        default_factory=list, description=" respondent_id для исключения (held-out)"
    )


class MatchingResponse(BaseModel):
    """Ответ POST /api/matching/find."""

    matches: list[dict[str, Any]]
    total: int
    corpus_size: int


@router.post("/matching/find", response_model=MatchingResponse)
async def find(req: MatchingRequest) -> MatchingResponse:
    """Находит ближайших респондентов к persona_dna в grounding-корпусе."""
    try:
        config = FindConfig(
            top_k=req.top_k,
            min_similarity=req.min_similarity,
            exclude_ids=set(req.exclude_ids) if req.exclude_ids else set(),
        )
        matches = find_similar_respondents(req.persona_dna, config)
        return MatchingResponse(
            matches=[m.to_dict() for m in matches],
            total=len(matches),
            corpus_size=165,  # канонический размер корпуса
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"matching failed: {e}") from e