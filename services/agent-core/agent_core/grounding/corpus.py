"""Доступ к grounding-корпусу из Python (задача #23).

Единственная точка чтения `data/grounding/unified_respondent_sessions.json`.
Прямое обращение к файлу из другого кода — ошибка: имена полей начнут
угадываться в каждом месте отдельно, и первая же опечатка станет тихим нулём
в метрике вместо падения.

Корпус — источник истины и read-only: 165 записей, 1.8 МБ, общие для всех
арендаторов. Он намеренно лежит файлом в git, а не в базе. Причина в том, что
от него зависит `persona_grounding` — единственная метрика с числовым порогом,
сверяющая сгенерированных персон с реальностью. Пока корпус в git, любое его
изменение видно в диффе и проходит ревью; в базе смена эталона не оставила бы
следа. Вдобавок `evals/check.py` обязан работать там, где никакой базы нет.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from statistics import mean

REPO = Path(__file__).resolve().parents[4]
DATASET = REPO / "data" / "grounding" / "unified_respondent_sessions.json"
META = REPO / "data" / "grounding" / "corpus.meta.json"
SCHEMA = REPO / "packages" / "shared" / "schemas" / "respondent-session.schema.json"

#: Пять базовых критериев. Порядок фиксирован — по нему считается калибровка.
CORE_SCORES = ("overall_impression", "plot", "acting", "music", "cinematography")


class CorpusError(RuntimeError):
    """Корпус недоступен или не соответствует схеме."""


@dataclass(frozen=True)
class CorpusMeta:
    version: int
    records: int
    sha256: str
    sources: tuple[str, ...]


def _read_json(path: Path) -> object:
    if not path.is_file():
        raise CorpusError(f"файл корпуса не найден: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusError(f"{path.name} не разбирается как JSON: {exc}") from exc


@lru_cache(maxsize=1)
def load_sessions() -> tuple[dict, ...]:
    """Все записи корпуса. Кортеж, а не список, — чтобы никто не дописал в кеш."""
    data = _read_json(DATASET)
    if not isinstance(data, list) or not data:
        raise CorpusError("корпус должен быть непустым массивом записей")
    return tuple(data)


@lru_cache(maxsize=1)
def load_meta() -> CorpusMeta:
    raw = _read_json(META)
    if not isinstance(raw, dict):
        raise CorpusError("corpus.meta.json должен быть объектом")
    try:
        return CorpusMeta(
            version=raw["version"],
            records=raw["records"],
            sha256=raw["sha256"],
            sources=tuple(raw["provenance"]["sources"]),
        )
    except (KeyError, TypeError) as exc:
        raise CorpusError(f"паспорт корпуса неполон: {exc}") from exc


def dataset_sha256() -> str:
    """Фактический хеш файла — для сверки с паспортом."""
    return hashlib.sha256(DATASET.read_bytes()).hexdigest()


def validate(strict: bool = True) -> list[str]:
    """Проверка корпуса по canonical JSON Schema.

    Возвращает список ошибок вида «respondent_id: путь — сообщение».
    При отсутствии jsonschema поднимает CorpusError, а не молча возвращает
    пустой список: «проверок не было» и «ошибок нет» — разные вещи, и путать
    их в метрике опаснее, чем упасть.
    """
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - зависит от среды
        raise CorpusError("нужен jsonschema>=4 (pip install 'jsonschema>=4')") from exc

    if not hasattr(jsonschema, "Draft202012Validator"):
        raise CorpusError("нужен jsonschema>=4: в установленной версии нет Draft 2020-12")

    schema = _read_json(SCHEMA)
    validator = jsonschema.Draft202012Validator(schema)

    errors: list[str] = []
    for record in load_sessions():
        rid = record.get("respondent_id", "<без id>")
        for err in validator.iter_errors(record):
            path = "/".join(str(p) for p in err.absolute_path) or "<корень>"
            errors.append(f"{rid}: {path} — {err.message}")
            if strict and len(errors) >= 50:
                return errors
    return errors


# ─── Выборки ──────────────────────────────────────────────────────────────


def by_source(source_file: str) -> tuple[dict, ...]:
    return tuple(r for r in load_sessions() if r["source_file"] == source_file)


def by_age_group(age_group: str) -> tuple[dict, ...]:
    return tuple(r for r in load_sessions() if r["socio_demographics"]["age_group"] == age_group)


def distribution(field: str) -> dict[str, float]:
    """Доли значений социодемографического поля. Именно это сравнивает
    persona_grounding с распределениями сгенерированных персон."""
    sessions = load_sessions()
    counts = Counter(r["socio_demographics"][field] for r in sessions)
    total = len(sessions)
    return {k: v / total for k, v in sorted(counts.items())}


def mean_scores() -> dict[str, float]:
    """Средние по пяти критериям. Порог калибровки |средние−реальные| ≤ 1.0."""
    sessions = load_sessions()
    return {k: mean(r["agora_core_scores_1_to_10"][k] for r in sessions) for k in CORE_SCORES}


def mean_nps() -> float:
    sessions = load_sessions()
    return mean(r["perception_and_retention"]["recommendation_nps_1_to_10"] for r in sessions)


def sources() -> tuple[str, ...]:
    return tuple(sorted({r["source_file"] for r in load_sessions()}))
