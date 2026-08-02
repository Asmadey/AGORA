"""POST /api/personas/generate — генерация синтетических персон (задача #5).

Принимает JSON-тело:

    {
        "size": 20,           // 1–100, по умолчанию 20
        "seed": 42,           // неотрицательное целое, по умолчанию 42
        "serial": null,       // фильтр по сериалу (опц.)
        "city": null,         // фильтр по городу (опц.)
        "segment": null,      // целевая аудитория (опц.)
        "use_llm": false      // через LLM-промпт (опц., требует ключ)
    }

Возвращает:

    {
        "personas": [ PersonaDNA, ... ],
        "seed": 42,
        "size": 20
    }

Детерминизм: один seed → один результат (CDD-тест проверяет diff == 0).
Гвардрейл: «ответ ограничен профилем» — персоны не выходят за рамки сегмента.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_core.persona.generator import (
    GenerationConfig,
    generate_personas,
)

router = APIRouter(prefix="/api", tags=["personas"])


class GenerateRequest(BaseModel):
    """Тело запроса POST /api/personas/generate."""

    size: int = Field(default=20, ge=1, le=500, description="Количество персон (1–500)")
    seed: int = Field(default=42, ge=0, description="Seed для детерминизма")
    serial: str | None = Field(default=None, description="Фильтр по сериалу")
    city: str | None = Field(default=None, description="Фильтр по городу")
    segment: str | None = Field(default=None, description="Целевая аудитория")
    use_llm: bool = Field(default=False, description="Генерация через LLM-промпт")


class GenerateResponse(BaseModel):
    """Ответ POST /api/personas/generate."""

    personas: list[dict[str, Any]]
    seed: int
    size: int


@router.post("/personas/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    """Генерирует ``req.size`` синтетических персон по методологии PRD §10."""
    try:
        config = GenerationConfig(
            size=req.size,
            seed=req.seed,
            serial=req.serial,
            city=req.city,
            segment=req.segment,
            use_llm=req.use_llm,
        )
        personas = generate_personas(config)
        return GenerateResponse(
            personas=personas,
            seed=config.seed,
            size=len(personas),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"generation failed: {e}") from e