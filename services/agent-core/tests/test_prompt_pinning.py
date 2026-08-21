"""
Промпты респондента берутся из снимка прогона, а не из файла в образе.

─── Что было ────────────────────────────────────────────────────────────────
Снимок промптов (Decision Log #10) собирается на запуске: `buildPromptsSnapshot`
пиннит id и версию КАЖДОГО активного промпта реестра, включая
`respondent.system` и `respondent.user`, и кладёт их в `tasks.prompts_snapshot`.
Смысл — воспроизводимость: правка в Промпт-студии между двумя прогонами не
должна менять результат задним числом.

Узел `evaluate_personas` звал `run_survey` без шаблонов, а тот при `None`
читает файлы из образа. То есть снимок для главного промпта продукта — того,
которым опрашиваются персоны, — записывался и не использовался. Правка в
Промпт-студии на прогон не влияла вовсе, а отчёт ссылался на версию, по которой
прогон не шёл.

Заметить это по результату нельзя: файл в образе и активная версия в реестре
совпадают, пока промпт не редактировали. Расхождение появляется ровно тогда,
когда им пользуются.

─── Почему проверка статическая ─────────────────────────────────────────────
`_prompt` ходит в Postgres за телом промпта по id из снимка. Поднимать базу
ради того, чтобы убедиться, что аргумент передан, несоразмерно: проверяется
свойство кода, а не поведение базы. Поведенческий уровень у этого свойства
один — сквозной прогон, где снимок и файл намеренно разведены.
"""

from __future__ import annotations

import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "agent_core"
NODES = CORE / "pipeline" / "nodes.py"


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(NODES.read_text("utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"в nodes.py нет функции {name}")


def _pinned_keys(func: ast.FunctionDef) -> set[str]:
    """Ключи промптов, которые узел спрашивает у снимка через `_prompt`."""
    keys: set[str] = set()
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_prompt"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            keys.add(str(node.args[0].value))
    return keys


def test_respondent_prompts_come_from_the_snapshot():
    """Узел опроса персон спрашивает оба своих промпта у снимка."""
    keys = _pinned_keys(_function("evaluate_personas"))
    assert {"respondent.system", "respondent.user"} <= keys, (
        f"evaluate_personas берёт из снимка только {sorted(keys)}: остальные "
        f"читаются файлом из образа, и пиннинг для них не работает"
    )


def test_snapshot_templates_are_passed_to_run_survey():
    """
    Полученные шаблоны действительно уходят в прогон.

    Отдельная проверка: `_prompt` можно позвать и не воспользоваться
    результатом — тогда первый тест зелёный, а поведение прежнее.
    """
    func = _function("evaluate_personas")
    for call in ast.walk(func):
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "run_survey"
        ):
            passed = {kw.arg for kw in call.keywords}
            assert {"system_template", "user_template"} <= passed, (
                f"run_survey зовётся без шаблонов ({sorted(passed)}) — при None "
                f"он читает файлы из образа, минуя снимок"
            )
            return
    raise AssertionError("в evaluate_personas нет вызова run_survey")


def test_fallback_to_file_is_reported():
    """
    Падение назад к файлу не бесшумно.

    `_prompt` возвращает пару (шаблон, причина деградации). Причина обязана
    доехать до отчёта: прогон по инструкции, которой нет в снимке, законен —
    незаметен он быть не должен.
    """
    source = ast.get_source_segment(NODES.read_text("utf-8"), _function("evaluate_personas"))
    assert source is not None
    assert "degraded" in source, (
        "evaluate_personas не сообщает о падении назад к файлу — прогон пойдёт "
        "по промпту, которого нет в снимке, и никто об этом не узнает"
    )
