"""
Воркер спрашивает только те таблицы, которые заводит схема.

Написан после того, как сквозной прогон упал на `relation "prompt_versions" does
not exist`. Таблицы с таким именем не было никогда: веб пиннит `prompts.id`, а
воркер читал `prompt_versions` — две стороны шва, написанные порознь и ни разу не
проверенные вместе.

Обычные тесты воркера этого не ловят: путь с пиннингом требует живой базы и на
машине без неё не выполняется. Поэтому проверка статическая — разбирает SQL
миграций и исходники, и работает в CI без Postgres.

Ценность здесь не в конкретной опечатке, а в классе: следующее несуществующее имя
таблицы упадёт на этом тесте, а не через восемьдесят секунд прогона после
оплаченных ffmpeg и транскрипции.
"""

from __future__ import annotations

import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
REPO = CORE.parents[1]
INIT = REPO / "infra" / "postgres" / "init"

#: `FROM x`, `JOIN x`, `INSERT INTO x`, `UPDATE x` в SQL внутри исходников.
#:
#: Только ЗАГЛАВНЫЕ ключевые слова, и это не стилистика. Регистронезависимый
#: шаблон ловит питоновское `from pathlib import Path` и выдаёт список из
#: полусотни «несуществующих таблиц» — проверка, тонущая в ложных срабатываниях,
#: перестаёт читаться и потому не работает. SQL в этом коде пишется заглавными.
_QUERY = re.compile(
    r"\b(?:FROM|JOIN|INSERT\s+INTO|UPDATE)\s+(?:public\.)?([a-z_][a-z0-9_]*)"
)

_CREATE = re.compile(
    r"CREATE\s+(?:TABLE|VIEW|MATERIALIZED\s+VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:public\.)?([a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)

#: Не таблицы: подзапросы, CTE и служебные имена, попадающие под тот же шаблон.
_NOT_TABLES = {
    "select", "values", "unnest", "generate_series", "lateral", "only",
    "set", "pg_policies", "pg_tables", "pg_class", "pg_roles", "pg_namespace",
}


def known_tables() -> set[str]:
    tables: set[str] = set()
    for sql in sorted(INIT.glob("*.sql")):
        tables |= {m.lower() for m in _CREATE.findall(sql.read_text("utf-8"))}
    return tables


def _without_comments(source: str) -> str:
    """
    Исходник без питоновских комментариев.

    Разбор всего файла подряд ловит объяснения наравне с кодом: комментарий,
    рассказывающий, почему в запросе не используется `EXTRACT(EPOCH FROM
    started_at)`, читается этим же шаблоном как обращение к таблице
    `started_at`. Проверка, срабатывающая на собственном объяснении, заставляет
    писать комментарии так, чтобы они нравились регулярке.

    Строки не трогаем: SQL живёт именно в них, и вырезать их значит выключить
    проверку целиком. Достаточно убрать `#` до конца строки, не тронув решётку
    внутри литерала.
    """
    out_lines: list[str] = []
    for line in source.splitlines():
        quote: str | None = None
        cut = len(line)
        i = 0
        while i < len(line):
            ch = line[i]
            if quote:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "#":
                cut = i
                break
            i += 1
        out_lines.append(line[:cut])
    return "\n".join(out_lines)


def queried_tables() -> dict[str, set[str]]:
    """Имя таблицы → файлы воркера, которые её спрашивают."""
    out: dict[str, set[str]] = {}
    for py in sorted((CORE / "agent_core").rglob("*.py")):
        text = _without_comments(py.read_text("utf-8"))
        for name in _QUERY.findall(text):
            low = name.lower()
            if low in _NOT_TABLES:
                continue
            out.setdefault(low, set()).add(str(py.relative_to(CORE)))
    return out


def test_migrations_declare_at_least_the_core_tables():
    """Страховка самого теста: пустой разбор SQL сделал бы его зелёным всегда."""
    tables = known_tables()
    assert {"prompts", "tasks", "personas"} <= tables, sorted(tables)


def test_worker_queries_only_existing_tables():
    tables = known_tables()
    missing = {
        name: sorted(files)
        for name, files in queried_tables().items()
        if name not in tables
    }
    assert not missing, (
        "воркер обращается к таблицам, которых нет в infra/postgres/init: "
        + "; ".join(f"{n} ({', '.join(f)})" for n, f in sorted(missing.items()))
    )
