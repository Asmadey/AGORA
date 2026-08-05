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

─── Почему проверяется установленность, а не строка в pyproject ─────────────
Сверять со списком в pyproject значило бы вести вторую копию: часть пакетов
приходит транзитивно и по делу (torch и numpy тянет pyannote.audio, и это
записано в комментарии рядом с зависимостью). Такой тест краснел бы на
правильном коде и его быстро бы отключили.

`find_spec` спрашивает у среды, разрешается ли имя. В CI окружение собирается
ровно из pyproject — значит незаявленный пакет там не установлен, и проверка
краснеет по существу, а не по расхождению двух списков.
"""

from __future__ import annotations

import ast
import sys
from importlib.util import find_spec
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "agent_core"

#: Имена, которые не являются внешними пакетами.
FIRST_PARTY = {"agent_core"}


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

    missing = {
        name: sorted(files)
        for name, files in found.items()
        if find_spec(name) is None
    }
    assert not missing, (
        "импортируется, но не установлено — значит не объявлено в pyproject: "
        + "; ".join(f"{n} ({', '.join(f)})" for n, f in missing.items())
    )


def test_model_client_is_declared():
    """
    Отдельным условием: клиент провайдера моделей.

    Общая проверка выше поймала бы и его, но при обновлении зависимостей легко
    ослабить её случайно. Здесь названа конкретная причина: без openai воркер не
    выполнит ни одной задачи, где участвует модель, — а таких три из четырёх.
    """
    assert find_spec("openai") is not None, (
        "openai не установлен: разбор кадров (#16), прогон респондентов (#18) и "
        "обогащение персон обращаются к нему во время работы"
    )
