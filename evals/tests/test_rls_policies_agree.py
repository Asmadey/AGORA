#!/usr/bin/env python3
"""
Политика, переопределённая поздней миграцией, совпадает с 03_rls.sql.

─── Зачем ────────────────────────────────────────────────────────────────────
`infra/postgres/migrate.sh` переприменяет 01_extensions.sql, 02_schema.sql и
03_rls.sql ПРИ КАЖДОМ ЗАПУСКЕ — это не разовые файлы, а канонический источник.
Поздние миграции обычно только ДОБАВЛЯЮТ политики, и тогда конфликта нет.

Но если поздняя миграция переопределяет политику, которая описана и в
03_rls.sql, первый же прогон `migrate.sh` молча вернёт старое определение.
Ни в диффе, ни в логах следа не останется: SQL отработает без ошибок, а
поведение продукта откатится.

§5 CLAUDE.md описывает ровно этот способ потерять правку — «следующий
migrate.sh молча вернёт схему к состоянию из репозитория». Так однажды исчез
FORCE ROW LEVEL SECURITY.

Проверка не запрещает переопределение: иногда оно нужно, как в миграции 52 для
уже развёрнутых баз. Она требует, чтобы ОБА определения говорили одно и то же.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

INIT = Path(__file__).resolve().parents[2] / "infra" / "postgres" / "init"
CANONICAL = INIT / "03_rls.sql"

#: `CREATE POLICY <имя> ON <таблица> … ;` — тело берём до точки с запятой.
POLICY = re.compile(
    r"CREATE\s+POLICY\s+(?P<name>[a-z0-9_]+)\s+ON\s+[a-z0-9_.]+(?P<body>.*?);",
    re.IGNORECASE | re.DOTALL,
)

results: list[tuple[str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, "OK" if ok else "FAIL"))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  ->  {detail}" if detail else ""))


def policies(path: Path) -> dict[str, str]:
    """Имя политики → её тело без комментариев и лишних пробелов."""
    text = path.read_text("utf-8")
    text = re.sub(r"--[^\n]*", "", text)
    return {
        m.group("name"): _normalize(m.group("body"))
        for m in POLICY.finditer(text)
    }


def _normalize(body: str) -> str:
    """
    Сравниваем СМЫСЛ, а не раскладку.

    Перенос строки внутри USING и лишний пробел у скобки ничего не меняют, а
    придираться к ним значило бы получить красный тест на переформатировании —
    и приучить к тому, что он краснеет зря.
    """
    flat = " ".join(body.split())
    flat = re.sub(r"\(\s+", "(", flat)
    flat = re.sub(r"\s+\)", ")", flat)
    return flat


print("== Политики RLS ==")

canonical = policies(CANONICAL)
check("03_rls.sql разобран", bool(canonical), f"политик: {len(canonical)}")

for path in sorted(INIT.glob("*.sql")):
    if path.name == CANONICAL.name:
        continue
    for name, body in policies(path).items():
        if name not in canonical:
            continue  # новая политика — конфликта нет
        check(
            f"{path.name}: {name} совпадает с 03_rls.sql",
            body == canonical[name],
            "" if body == canonical[name] else (
                "определения разошлись — migrate.sh молча вернёт версию из "
                f"03_rls.sql.\n        миграция:  {body[:160]}\n        03_rls.sql: {canonical[name][:160]}"
            ),
        )

failed = [name for name, status in results if status == "FAIL"]
print()
if failed:
    print(f"RED — расходящихся политик: {len(failed)}")
    for name in failed:
        print(f"  · {name}")
    sys.exit(1)

print(f"GREEN — определения политик согласованы (проверок: {len(results)})")
