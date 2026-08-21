"""
Прогресс генерации аудитории доезжает до базы, а не в открытую транзакцию.

─── Что было ────────────────────────────────────────────────────────────────
Первая редакция `generate_audience` держала одну транзакцию открытой всю
генерацию и писала прогресс в неё. Отказ был двойным, и обе половины тихие:

1. Незакоммиченную строку не видит читатель. Список наборов опрашивается
   извне и показывал бы «0 из 60» до самого конца, каким бы ни был счётчик
   внутри.
2. `tenant_scope` ставит арендатора транзакционно (`set_config(…, true)`), и
   `SET LOCAL ROLE` — тоже. Коммит изнутри `conn.transaction()` psycopg
   отвергает, а обёртка прогресса исключение глотает.

На экране это выглядело так: «0 из 6» тридцать секунд, потом сразу «6 из 6».
Набор наполнялся правильно, счётчик не работал ни разу — то есть дефект
выглядел как быстрая генерация, а не как сломанный прогресс. Заодно одна
транзакция висела открытой всю генерацию, держа снимок и мешая автовакууму.

─── Почему проверка такая ───────────────────────────────────────────────────
Поведенческая проверка требует живого Postgres, а свойство, которое надо
удержать, — структурное: «обращение к модели не находится внутри открытой
транзакции». Оно проверяется по дереву разбора и не зависит от среды.

Проверять «прогресс записался» на живой базе тоже стоит, но это делает
сквозной прогон: там счётчик виден на экране, и именно там дефект и нашёлся.
"""

from __future__ import annotations

import ast
from pathlib import Path

TASKS = Path(__file__).resolve().parents[1] / "agent_core" / "persona" / "tasks.py"


def _generate_audience() -> ast.FunctionDef:
    tree = ast.parse(TASKS.read_text("utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "generate_audience":
            return node
    raise AssertionError("в persona/tasks.py нет generate_audience")


def _opens_connection(item: ast.withitem) -> bool:
    """`with psycopg.connect(...)` или `with tenant_scope(...)`."""
    call = item.context_expr
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    return name in {"connect", "tenant_scope"}


def _calls_inside_transactions(func: ast.FunctionDef) -> set[str]:
    """Имена функций, вызываемых внутри открытой транзакции."""
    inside: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.depth = 0

        def visit_With(self, node: ast.With) -> None:
            opened = any(_opens_connection(item) for item in node.items)
            self.depth += 1 if opened else 0
            for child in node.body:
                self.visit(child)
            self.depth -= 1 if opened else 0

        def visit_Call(self, node: ast.Call) -> None:
            if self.depth:
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                inside.add(name)
            self.generic_visit(node)

    Visitor().visit(func)
    return inside


def test_enrichment_runs_outside_any_transaction():
    """
    Обогащение — минуты вызовов модели. Внутри транзакции ему не место.

    Не только из-за прогресса: транзакция, открытая на всё время генерации,
    держит снимок и мешает автовакууму. Прогресс — просто то, обо что дефект
    споткнулся первым.
    """
    inside = _calls_inside_transactions(_generate_audience())
    assert "enrich_personas" not in inside, (
        "enrich_personas зовётся внутри открытой транзакции: прогресс из неё не "
        "виден читателю, а коммит изнутри tenant_scope psycopg отвергает"
    )


def test_progress_updates_have_their_own_transaction():
    """
    Каждое обновление прогресса — своя короткая транзакция.

    Тенант-контекст живёт ровно транзакцию: продлить его, не продлевая её,
    нельзя. Значит либо своё соединение на обновление, либо прогресс, которого
    никто не увидит.
    """
    source = TASKS.read_text("utf-8")
    tree = ast.parse(source)
    updater = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_update"),
        None,
    )
    assert updater is not None, (
        "нет отдельной функции обновления: прогресс пишется по месту, а значит "
        "в транзакцию вызывающего"
    )
    body = ast.get_source_segment(source, updater) or ""
    assert "connect" in body and "tenant_scope" in body, (
        "_update не открывает собственное соединение с тенант-контекстом"
    )


def test_progress_is_written_with_a_step():
    """
    Прогресс пишется не после каждой персоны.

    При пятистах персонах это пятьсот транзакций по строке, которую в это же
    время опрашивает список. Шаг — компромисс: раз в несколько секунд заметно
    глазу и незаметно базе.
    """
    assert "PROGRESS_EVERY" in TASKS.read_text("utf-8"), (
        "шага прогресса нет — либо обновление на каждую персону, либо прогресса "
        "нет вовсе"
    )


def test_the_check_above_would_catch_the_original_defect():
    """
    Канарейка: обход находит вызов, спрятанный в транзакции.

    Без неё зелёный `test_enrichment_runs_outside_any_transaction` ничего не
    доказывает — он одинаково зелен и когда дефекта нет, и когда обход просто
    не умеет его видеть.
    """
    broken = ast.parse(
        "def generate_audience(self, payload):\n"
        "    with psycopg.connect(dsn) as conn, tenant_scope(conn, tid) as cur:\n"
        "        outcome = enrich_personas(personas, on_progress=report)\n"
    ).body[0]
    assert isinstance(broken, ast.FunctionDef)
    assert "enrich_personas" in _calls_inside_transactions(broken)
