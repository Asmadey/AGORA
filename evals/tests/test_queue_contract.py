#!/usr/bin/env python3
"""
Имена задач, которые веб кладёт в очередь, существуют в воркере.

Это не задача из графа, а проверка шва — того самого класса, которым уже
дважды оплачен полный прогон.

─── Почему шов опасен именно здесь ──────────────────────────────────────────
Клиента Celery для Node нет. `apps/web/lib/server/queue.ts` собирает сообщение
протокола 2 руками и кладёт его в список Valkey. Со стороны веба успех — это
успешный `LPUSH`: сообщение принято списком, маршрут отвечает 202, строка
появляется на экране.

Дальше сообщение разбирает воркер. Если имени задачи нет в реестре, он пишет в
свой лог «Received unregistered task» и сообщение теряется. Наружу это не
выходит вообще: запись висит в `generating` или `QUEUED` ровно так же, как при
медленной генерации. Отличить одно от другого по экрану нельзя.

Имя попадает в реестр двумя условиями сразу, и оба легко забыть по отдельности:

1. декоратор `@app.task(name="agora.…")` на функции;
2. модуль с этой функцией — в списке `include` приложения Celery.

Второе особенно тихое: модуль существует, тест воркера его импортирует
напрямую и зелёный, а воркер в проде его не импортирует и задачи не знает.
Ровно так `agent_core.persona.tasks` был бы невидим, если бы `include` забыли
дополнить.

─── Почему статически ───────────────────────────────────────────────────────
Поднимать Celery ради этого не нужно и вредно: реестр собирается импортом, а
импорт `pipeline.tasks` тянет langgraph и torch. Разбор исходников даёт тот же
ответ и работает на любой машине — а поведенческую проверку даёт сквозной
прогон, где сообщение действительно доезжает.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "services" / "agent-core" / "agent_core"
QUEUE_TS = REPO / "apps" / "web" / "lib" / "server" / "queue.ts"
CELERY_APP = CORE / "celery_app.py"

PASS, FAIL = "OK", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail and not ok else ""))


# ─── Что шлёт веб ────────────────────────────────────────────────────────────
#
# Имя задачи в queue.ts — это либо значение по умолчанию параметра
# `taskName` у buildMessage, либо третий аргумент вызова. Оба вида берутся
# одной регуляркой по строковым литералам «agora.…»: перечислять их вручную
# значило бы завести третье место, где записан тот же список.

web_src = QUEUE_TS.read_text("utf-8") if QUEUE_TS.exists() else ""
check("apps/web/lib/server/queue.ts существует", bool(web_src))

web_names = sorted(set(re.findall(r'"(agora\.[a-z_]+)"', web_src)))
check(
    "веб шлёт хотя бы одно имя задачи",
    bool(web_names),
    "в queue.ts не найдено ни одного литерала agora.* — либо имена собираются "
    "динамически (тогда эта проверка бессильна), либо файл не тот",
)
print(f"        веб отправляет: {', '.join(web_names) or '—'}")


# ─── Что знает воркер ────────────────────────────────────────────────────────

registered: dict[str, str] = {}  # имя задачи → модуль, где она объявлена
for path in sorted(CORE.rglob("*.py")):
    try:
        tree = ast.parse(path.read_text("utf-8"))
    except SyntaxError:
        continue
    module = ".".join(path.relative_to(CORE.parent).with_suffix("").parts)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            for kw in deco.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    value = kw.value.value
                    if isinstance(value, str) and value.startswith("agora."):
                        registered[value] = module

print(f"        воркер объявляет: {', '.join(sorted(registered)) or '—'}")


# ─── include: объявить мало, надо ещё импортировать ──────────────────────────

app_src = CELERY_APP.read_text("utf-8") if CELERY_APP.exists() else ""
included = set(re.findall(r'"(agent_core\.[A-Za-z_.]+)"', app_src))
print(f"        include: {', '.join(sorted(included)) or '—'}")

for name in web_names:
    module = registered.get(name)
    check(
        f"{name} объявлена в воркере",
        module is not None,
        f"веб кладёт в очередь «{name}», а @app.task с таким именем в agent_core нет: "
        f"воркер ответит «Received unregistered task», и сообщение пропадёт молча",
    )
    if module is None:
        continue
    # Задача в celery_app.py (ping) в include не нуждается: модуль приложения
    # импортируется сам собой.
    if module == "agent_core.celery_app":
        continue
    check(
        f"{name} импортируется приложением (include)",
        module in included,
        f"«{name}» объявлена в {module}, но этого модуля нет в include= "
        f"celery_app.py: воркер поднимется, очередь разберёт и на задаче "
        f"ответит «Received unregistered task»",
    )


# ─── Обратная сторона: имя совпадает с идентификатором строки ────────────────
#
# Для генерации аудитории id celery-задачи намеренно равен id набора персон:
# по нему воркер находит строку, которую наполняет, а повтор Celery не создаёт
# второй набор. Требование неочевидное, поэтому записано проверкой.

check(
    "генерация аудитории берёт id задачи от набора персон",
    "const taskId = payload.persona_set_id" in web_src,
    "id celery-задачи должен совпадать с id набора: иначе повтор Celery заведёт "
    "второй набор, а первый останется в generating навсегда",
)
check(
    "прогон берёт id задачи от строки прогона",
    "const taskId = payload.task_id" in web_src,
    "id celery-задачи должен совпадать с id прогона: по нему воркер находит "
    "чекпоинт LangGraph, иначе ретрай начнёт прогон с нуля",
)


print()
n_fail = sum(1 for _, s, _ in results if s == FAIL)
print(f"Итог: OK={len(results) - n_fail} FAIL={n_fail}")
if n_fail:
    print("\nНевыполненные условия:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  · {name}" + (f" — {detail}" if detail else ""))
sys.exit(1 if n_fail else 0)
