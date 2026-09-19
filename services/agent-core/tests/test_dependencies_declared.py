"""
Всё, что воркер импортирует, должно быть установлено.

─── Почему такой проверки не хватало ────────────────────────────────────────
`openai` не был объявлен в зависимостях, хотя его импортируют четыре модуля:
разбор кадров (#16), прогон респондентов (#18), обогащение персон и дистилляция
портретов. Ни сборка образа, ни тесты, ни healthcheck этого не заметили.

Причина в приёме, который сам по себе правильный: тяжёлые импорты сделаны
ВНУТРИ функций, чтобы не платить за них там, где модель не нужна. Побочный
эффект — модуль импортируется без ошибки, образ собирается, воркер поднимается
healthy, а ModuleNotFoundError ждёт первого обращения к модели. То есть отказ
наступает после оплаченных ffmpeg, транскрипции и разбора кадров, и выглядит
как сбой прогона, а не как незаявленная зависимость.

─── Почему проверяется и pyproject, и установленность ────────────────────────
`find_spec` спрашивает у среды, разрешается ли имя, но на хосте разработчика
тяжёлых пакетов нет намеренно. Поэтому отсутствие разделяется на два случая:
незаявленный импорт остаётся дефектом, а заявленный пакет, отсутствующий в этой
среде, становится честным SKIP с указанием запуска в образе воркера.

Имена импортов и distributions не всегда совпадают. Алиасы ниже учитывают
публичные имена пакетов и транзитивные импорты, которые приходят через
объявленные зависимости, чтобы не вести второй список версий.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "agent_core"
PYPROJECT = PKG.parent / "pyproject.toml"

#: Имена, которые не являются внешними пакетами.
FIRST_PARTY = {"agent_core"}

# Имя import обычно совпадает с именем distribution после PEP 503-нормализации,
# но эти пакеты требуют знания границы между ними. Значение - distribution,
# объявленный напрямую или транзитивно через него.
IMPORT_DISTRIBUTION_ALIASES = {
    "botocore": "boto3",
    "faster_whisper": "faster-whisper",
    "numpy": "pyannote.audio",
    "pdfminer": "pdfminer.six",
    "pyannote": "pyannote.audio",
    "scenedetect": "scenedetect",
    "sherpa_onnx": "sherpa-onnx",
    "torch": "pyannote.audio",
}


def _normalise_distribution(name: str) -> str:
    """Сводит имя distribution к сравнению по правилам PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


def declared_distributions(path: Path = PYPROJECT) -> set[str]:
    """Возвращает имена пакетов из основных и dev-зависимостей pyproject."""
    document = tomllib.loads(path.read_text("utf-8"))
    project = document["project"]
    requirements = list(project.get("dependencies", []))
    for optional in project.get("optional-dependencies", {}).values():
        requirements.extend(optional)

    declared: set[str] = set()
    for requirement in requirements:
        match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
        if not match:
            raise AssertionError(f"не удалось разобрать зависимость: {requirement!r}")
        declared.add(_normalise_distribution(match.group(1)))
    return declared


def _importable(module: str) -> bool:
    """Возвращает False и для отсутствующего родителя составного импорта."""
    try:
        return find_spec(module) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def _is_declared(import_name: str, declared: set[str]) -> bool:
    root = import_name.split(".", 1)[0]
    candidates = {_normalise_distribution(root)}
    alias = IMPORT_DISTRIBUTION_ALIASES.get(root)
    if alias:
        candidates.add(_normalise_distribution(alias))
    return bool(candidates & declared)


def classify_missing_imports(
    found: dict[str, set[str]],
    declared: set[str],
    importable: Callable[[str], bool] = _importable,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Разделяет импорты на незаявленные и заявленные, но отсутствующие."""
    undeclared: dict[str, set[str]] = {}
    declared_but_missing: dict[str, set[str]] = {}
    for name, files in found.items():
        if not _is_declared(name, declared):
            # Декларация обязательна даже тогда, когда пакет случайно приехал
            # транзитивно или уже установлен в окружении теста.
            undeclared[name] = files
        elif not importable(name):
            # Заявленный, но отсутствующий пакет - честный SKIP для среды.
            declared_but_missing[name] = files
    return undeclared, declared_but_missing


def top_level_imports(source: str) -> set[str]:
    """Корневые имена всех импортов файла, включая объявленные внутри функций."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # level > 0 — относительный импорт внутри пакета, внешним быть не может.
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def external_imports() -> dict[str, set[str]]:
    """Внешние импорты пакета: {имя пакета: файлы, где встречается}."""
    found: dict[str, set[str]] = {}
    for path in sorted(PKG.rglob("*.py")):
        for name in top_level_imports(path.read_text("utf-8")):
            if name in FIRST_PARTY or name in sys.stdlib_module_names:
                continue
            found.setdefault(name, set()).add(str(path.relative_to(PKG.parent)))
    return found


def test_every_import_resolves():
    found = external_imports()
    assert found, "внешних импортов не найдено — проверка что-то не разобрала"

    undeclared, declared_but_missing = classify_missing_imports(
        found,
        declared_distributions(),
    )
    assert not undeclared, (
        "импортируется, но не установлено — значит не объявлено в pyproject: "
        + "; ".join(
            f"{n} ({', '.join(sorted(files))})" for n, files in undeclared.items()
        )
    )
    if declared_but_missing:
        details = "; ".join(
            f"{name} ({', '.join(sorted(files))})"
            for name, files in declared_but_missing.items()
        )
        pytest.skip(
            "импорт объявлен в pyproject, но не установлен в этой среде: "
            f"{details}. Запустите тест в образе воркера: "
            "./evals/run_in_worker.sh -- python -m pytest services/agent-core/tests"
        )


def test_model_client_is_declared():
    """
    Отдельным условием: клиент провайдера моделей.

    Общая проверка выше поймала бы и его, но при обновлении зависимостей легко
    ослабить её случайно. Здесь названа конкретная причина: без openai воркер не
    выполнит ни одной задачи, где участвует модель, — а таких три из четырёх.
    """
    declared = declared_distributions()
    if not _is_declared("openai", declared):
        pytest.fail(
            "openai импортируется кодом, но не объявлен в pyproject: разбор кадров (#16), "
            "прогон респондентов (#18) и обогащение персон обращаются к нему во время работы"
        )
    if not _importable("openai"):
        pytest.skip(
            "openai объявлен в pyproject, но не установлен в этой среде. "
            "Запустите тест в образе воркера: "
            "./evals/run_in_worker.sh -- python -m pytest services/agent-core/tests"
        )
