"""
Число попыток пересоздания персоны приходит из настроек, а не из константы.

─── Замер, из которого это следует ──────────────────────────────────────────
17.09.2026 прочитаны `personas.validation` на боевом — три набора, 70 персон:

    попыток   персон   осталось забракованными
       1        43              0
       2        14              0
       3        13              4

Пересоздание СПАСЛО 23 из 27 забракованных — механизм исправен. Но стоит он
дорого: 220 вызовов модели вместо 140, то есть **57 % накладных**, и увидеть это
можно было только запросом к базе.

Число попыток при этом было прибито константой `MAX_ATTEMPTS = 3`, тогда как у
соседнего механизма — переспроса ОТВЕТОВ — настройка есть, с потолком в
интерфейсе и разбором в `RequestionConfig.for_task`. Два похожих механизма с
непохожей судьбой.

Правка убирает асимметрию и НИЧЕГО НЕ УЛУЧШАЕТ сама по себе: доля успеха на
попытку держится около 50–70 %, четвёртая попытка спасла бы 2–3 персоны из 4
ценой четырёх полных циклов. Настоящий рычаг — первая попытка.

─── Про стык ────────────────────────────────────────────────────────────────
Второй тест здесь важнее первого. Разбор настройки можно написать, покрыть
тестами и не подключить — тогда `validate_set` продолжит считать по константе, а
настройка станет ручкой, которая ничего не крутит. Этот дефект в проекте уже
случался (см. `test_requestion.py`, раздел «Стык с узлом»), и повторять его
незачем.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agent_core.config import PersonaAttemptsConfig
from agent_core.persona.validate import MAX_ATTEMPTS

TASKS = Path(__file__).resolve().parents[1] / "agent_core" / "persona" / "tasks.py"


# ─── Разбор настройки ────────────────────────────────────────────────────────


def test_default_matches_the_old_constant():
    """
    Умолчание — прежние три.

    Иначе появление ручки молча поменяло бы поведение продукта, и все наборы
    после этой правки стали бы несравнимы с теми, что уже лежат в базе.
    """
    assert PersonaAttemptsConfig.defaults().attempts == MAX_ATTEMPTS == 3


def test_missing_snapshot_is_the_default():
    """Настройки, сохранённые до появления поля, его не содержат."""
    assert PersonaAttemptsConfig.for_task(None).attempts == 3
    assert PersonaAttemptsConfig.for_task({}).attempts == 3


def test_value_from_the_snapshot_wins():
    assert PersonaAttemptsConfig.for_task({"personaAttempts": 1}).attempts == 1
    assert PersonaAttemptsConfig.for_task({"personaAttempts": 5}).attempts == 5


def test_out_of_range_is_refused_not_clamped():
    """
    Обрезка означала бы, что человек видит в настройках одно, а прогон исполняет
    другое. Ноль отвергается отдельно: попыток не бывает меньше одной, и «не
    проверять вовсе» — это другое решение.
    """
    for bad in (0, -1, PersonaAttemptsConfig.MAX + 1):
        with pytest.raises(ValueError):
            PersonaAttemptsConfig.for_task({"personaAttempts": bad})


def test_garbage_is_refused():
    for bad in ("три", None if False else "", [3]):
        with pytest.raises(ValueError):
            PersonaAttemptsConfig.for_task({"personaAttempts": bad})


# ─── Стык: настройка доезжает до validate_set ────────────────────────────────


def test_task_passes_attempts_to_validate_set():
    """
    `validate_set` вызывается с `max_attempts` из настроек.

    Разбор через `ast`, а не грепом: имя встречается и в комментарии, и в
    соседнем коде, а нас интересует аргумент именно этого вызова.
    """
    tree = ast.parse(TASKS.read_text("utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_set"
    ]
    assert calls, "в tasks.py нет вызова validate_set — тест устарел"

    for call in calls:
        passed = {kw.arg for kw in call.keywords}
        assert "max_attempts" in passed, (
            f"validate_set вызван без max_attempts (строка {call.lineno}): настройка "
            f"осталась ручкой, которая ничего не крутит. Передано: "
            f"{sorted(n for n in passed if n)}"
        )


def test_task_reads_the_snapshot_not_a_literal():
    """
    Значение берётся из снимка настроек задачи.

    Прибитое число в вызове удовлетворило бы тест выше и не удовлетворило бы
    смысл: снимок фиксируется на момент запуска, чтобы настройку нельзя было
    сменить, пока задача стоит в очереди.
    """
    source = TASKS.read_text("utf-8")
    assert "PersonaAttemptsConfig" in source, (
        "tasks.py не читает PersonaAttemptsConfig — значит значение взято откуда-то ещё"
    )
    assert "settings_snapshot" in source, "снимок настроек в задаче не читается"
