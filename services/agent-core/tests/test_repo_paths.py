"""
Файлы, которые воркеру нужны в работе, находятся и в репозитории, и в образе.

─── Как это нашлось ─────────────────────────────────────────────────────────
Генерация аудитории переехала из веба в воркер — и упала на первом же запуске:

    FileNotFoundError: '/data/grounding/unified_respondent_sessions.json'

Две причины сразу, и обе невидимы из репозитория:

1. `infra/worker.Dockerfile` копирует в образ `services/agent-core/`,
   `packages/shared/` и `prompts/`, но НЕ `data/`. Корпуса в воркере не было
   вовсе — просто раньше его оттуда никто не спрашивал.
2. Путь считался как `Path(__file__).parents[…] / "data" / …`, то есть под одну
   раскладку — репозиторий. В образе исходники лежат в `/app/agent_core/`, и та
   же арифметика даёт `/data/grounding/…`, то есть корень файловой системы.

Второе опаснее первого: даже после копирования файла путь остался бы неверным,
и отказ выглядел бы так же.

─── Почему тест такой ───────────────────────────────────────────────────────
Проверяется не «файл лежит там-то», а «резолвер его находит» — то есть свойство,
которое переживёт смену раскладки. И отдельно, статически, проверяется сам
Dockerfile: файл, который резолвер найдёт в репозитории и не найдёт в образе,
даёт зелёный тест на машине разработчика и отказ в продакшене.

Ровно эту раскладку уже умеет `_find_prompt` в двух модулях — что и есть повод
завести один резолвер вместо третьей копии.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WORKER_DOCKERFILE = REPO / "infra" / "worker.Dockerfile"


def test_corpus_is_found_by_the_resolver():
    """Корпус находится тем же способом, что и промпты, а не арифметикой путей."""
    from agent_core.paths import find_data_file

    corpus = find_data_file("grounding/unified_respondent_sessions.json")
    assert corpus is not None, "корпус не найден резолвером"
    assert corpus.exists(), corpus


def test_generator_uses_the_resolver():
    """
    Генератор берёт корпус у резолвера.

    Проверка на класс, а не на файл: модуль, вычисляющий путь сам, снова
    разойдётся с раскладкой образа — и снова только в продакшене.
    """
    generator = REPO / "services" / "agent-core" / "agent_core" / "persona" / "generator.py"
    source = generator.read_text("utf-8")
    assert "find_data_file" in source, (
        "generator.py вычисляет путь к корпусу самостоятельно — в образе воркера "
        "такая арифметика даёт /data/grounding/…"
    )


def test_worker_image_carries_the_data_directory():
    """
    Образ воркера везёт каталог data.

    Статически по Dockerfile: файл, который резолвер найдёт в репозитории и не
    найдёт в образе, даёт зелёный тест у разработчика и отказ в продакшене —
    ровно то, что и случилось.
    """
    dockerfile = WORKER_DOCKERFILE.read_text("utf-8")
    copies_data = any(
        line.strip().startswith("COPY") and " data/" in line
        for line in dockerfile.splitlines()
    )
    assert copies_data, (
        "infra/worker.Dockerfile не копирует data/ — корпус в образе отсутствует, "
        "и генерация аудитории падает с FileNotFoundError"
    )
